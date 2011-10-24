# -*- coding: utf-8 -*-
import re
from copy import deepcopy
from memoized import memoized
from collections import defaultdict

from pdb import set_trace as ST

from noclobberdict import NoClobberDict
from orderedset import OrderedSet
import datapflex
from collect_dpf import Column, MSColumn


def comm(a, b):
    sa, sb = map(OrderedSet, (a, b))
    return (sa.difference(sb), sb.difference(sa),
            OrderedSet.intersection(sa, sb))


def unique(iterable):
    return len(set(iterable)) == 1



class Kyub(object):
    def __init__(self, factors, readouts, table):
        nfactors = len(factors)
        def valid_coords(c):
            return (hasattr(c, '__iter__') and
                    hasattr(c, '__len__') and
                    len(c) == nfactors)

        assert all(map(valid_coords, table.keys()))

        tmp = [tuple(sorted(v.keys())) for v in table.values()]
        assert unique(tmp + [tuple(sorted(readouts))])

        self.factors = factors
        self.readouts = readouts
        self.table = table


    @property
    @memoized
    def coords(self):
        return sorted(self.table.keys())


    @staticmethod
    def _subdict(dict_, *wanted):
        if len(wanted) == 0 or all([w is None for w in wanted]):
            return deepcopy(dict_)
        w = dict_.keys() if wanted[0] is None else wanted[0]
        return dict((k, Kyub._subdict(dict_[k], *wanted[1:])) for k in w)


    def __getitem__(self, key):
        return self.table[key]


    def subkyub(self, coords=None, readouts=None):
        return Kyub(self.factors,
                    self.readouts if readouts is None else readouts,
                    Kyub._subdict(self.table, coords, readouts))


    def __copy__(self):
        return Kyub(self.factors, self.readouts, self.table)


    def __deepcopy__(self, memo):
        ret = self.__copy__()
        ret.__dict__ = deepcopy(self.__dict__, memo)
        return ret


    @staticmethod
    def _get_perm(s, t):
        """
        Return the list p such that t[i] == s[p[i]] for all i.

        The arguments s and t must be duplicate-free iterables of known
        length such that t is a permutation of s (or, equivalently, s is a
        permutation of t).

        The following invariants will always hold for any valid iterables
        s and t:

            list(t) == [s[i] for i in _get_perm(s, t)]
            range(len(s)) == _get_perm(s, s)
        """

        n = len(s)
        assert n == len(set(s))
        assert sorted(s) == sorted(t)
        if s == t:
            return range(n)
        i = dict((k, j) for j, k in enumerate(s))
        return [i[k] for k in t]


    def reorder_factors(self, factors):
        ret = deepcopy(self)
        f = self.factors
        if factors != f:
            ret.factors = factors[:]
            p = Kyub._get_perm(f, factors)
            ret.table = dict((tuple([k[i] for i in p]), v)
                             for k, v in self.table.items())
        return ret


    def reorder_readouts(self, readouts):
        ret = deepcopy(self)
        if readouts != self.readouts:
            ret.readouts = readouts[:]
        return ret

    def get_treatment_column(self, header):
        i = self.factors.index(header)
        return [c[i] for c in self.coords]

    def get_column(self, header):
        t = self.table
        coords = self.coords
        return [t[c][header] for c in coords]


    @classmethod
    def conform(cls, a, b):
        a_factors, b_factors = a.factors, b.factors
        nfactors = len(a_factors)
        if len(b_factors) != nfactors:
            raise TypeError('Different numbers of factors.')

        if sorted(a_factors) != sorted(b_factors):
            raise TypeError('Different factors.')

        if a_factors != b_factors:
            diffs.append('Differently ordered factors.')
            b = b.reorder_factors(a_factors)

        return a, b


    @classmethod
    def merge(cls, a, *rest):
        allk = [a] + ([None] * len(rest))
        for i, b in enumerate(rest):
            _, allk[i + 1] = cls.conform(a, b)

        readouts = []
        seen = set()
        for r in sum([list(k.readouts) for k in allk], []):
            if r not in seen:
                readouts.append(r)
                seen.add(r)

        table = defaultdict(NoClobberDict)
        rset = set(readouts)
        for coords, data in sum([list(k.table.items()) for k in allk], []):
            assert all([k in rset for k in data.keys()])
            st = table[coords]
            st.update(data)
            for r in readouts:
                if r not in st:
                    st[r] = u''

        return Kyub(a.factors, readouts, table)


    @classmethod
    def diff(cls, a, b):
        a_factors, b_factors = a.factors, b.factors
        nfactors = len(a_factors)
        if len(b_factors) != nfactors:
            return('Different numbers of factors.')

        orig_factors = a_factors
        diffs = []
        if sorted(a_factors) != sorted(b_factors):
            def _strip_units(f):
                return re.sub(r'=.*$', '', f)
            a_factors, b_factors = (map(_strip_units, fs)
                                    for fs in (a_factors, b_factors))

            if sorted(a_factors) != sorted(b_factors):
                def _normalize_factors(f):
                    return re.sub(r'_name', '', f)
                a_factors, b_factors = (map(_normalize_factors, fs)
                                        for fs in (a_factors, b_factors))
                if sorted(a_factors) != sorted(b_factors):
                    return('%s vs %s' % (a_factors, b_factors))
                    return('Different factors.')
                diffs.append('Factors differ in details.')
            else:
                diffs.append('Factors differ in units.')

        if a_factors != b_factors:
            diffs.append('Differently ordered factors.')
            b = b.reorder_factors(a_factors)
            b_factors = a_factors

        def _record(first, second, label):
            d = locals()
            indent = u'  '
            for s in u'first', u'second':
                r = d[s]
                if not r:
                    continue
                diffs.append((u"""
%s(s) found only in %s kyub:
%s%s""" % (label, s, indent, (u'\n' + indent).join(r))).lstrip())
        
        a_readouts, b_readouts, common_readouts = comm(a.readouts, b.readouts)

        _record(a_readouts, b_readouts, u'readout')

        a_coords, b_coords, common_coords = comm(a.coords, b.coords)

        def _format_coords(cs):
            return [u','.join(c) for c in cs]

        _record(_format_coords(a_coords), _format_coords(b_coords), u'coord')

        diff_table = dict((rh, dict((ch, abs(float(at[ch]) - float(bt[ch])))
                                    for ch in common_readouts))
                           for rh, at, bt in
                          ((rh, a[rh], b[rh]) for rh in common_coords))

        return diffs, Kyub(orig_factors, common_readouts, diff_table)



def diff(path_a, path_b):
    def _getkyub(path):
        return Kyub(*datapflex.read_datapflex(path))

    diffs, dkyub = Kyub.diff(*map(_getkyub, (path_a, path_b)))
    return '\n'.join(diffs), dkyub
#     for ch in dkyub.readouts:
#         m = str(max(dkyub.get_column(ch)))
#         if m != '0.0':
#             print '%s: %s' % (ch, str(m))
#     return diffs, dkyub

if __name__ == '__main__DISCARD':
    from glob import glob
    import os.path as op

    irdir = '/home/gfb2/IR'
    dpdirs0, dpdirs1 = dpdirs = [op.join(irdir, d)
                                 for d in 'DATAPFLEX', 'DATAPFLEX_111018T']

    expected_template = {
        u'GF': u"""
Factors differ in details.
coord(s) found only in first kyub:
  %(assay)s,CTRL,0,0
  %(assay)s,CTRL,0,10
  %(assay)s,CTRL,0,30
  %(assay)s,CTRL,0,90
coord(s) found only in second kyub:
  %(assay)s,CTRL-GF-1,0,10
  %(assay)s,CTRL-GF-1,0,30
  %(assay)s,CTRL-GF-1,0,90
  %(assay)s,CTRL-GF-100,0,10
  %(assay)s,CTRL-GF-100,0,30
  %(assay)s,CTRL-GF-100,0,90
  """.strip(),
        u'CK': u"""
Factors differ in details.
readout(s) found only in first kyub:
  NF-κB-m-488
  NF-κB-m-488=stdev
  NF-κB-m-647
  NF-κB-m-647=stdev
readout(s) found only in second kyub:
  NF-κB-m-488 (ncr)
  NF-κB-m-488 (ncr)=stdev
  NF-κB-m-647 (ncr)
  NF-κB-m-647 (ncr)=stdev
coord(s) found only in first kyub:
  %(assay)s,CTRL,0,0
  %(assay)s,CTRL,0,10
  %(assay)s,CTRL,0,30
  %(assay)s,CTRL,0,90
coord(s) found only in second kyub:
  %(assay)s,CTRL-CK-L-1,0,10
  %(assay)s,CTRL-CK-L-1,0,30
  %(assay)s,CTRL-CK-L-1,0,90
  %(assay)s,CTRL-CK-L-100,0,10
  %(assay)s,CTRL-CK-L-100,0,30
  %(assay)s,CTRL-CK-L-100,0,90
  %(assay)s,CTRL-CK-R-1,0,10
  %(assay)s,CTRL-CK-R-1,0,30
  %(assay)s,CTRL-CK-R-1,0,90
  %(assay)s,CTRL-CK-R-100,0,10
  %(assay)s,CTRL-CK-R-100,0,30
  %(assay)s,CTRL-CK-R-100,0,90
  """.strip(),
        }

    for p in sorted(glob('scans/linkfarm/*')):
        assay = op.basename(p)
        for z in ('GF', 'CK'):
            f0, f1 = fs = [op.join(d, '%s_%s.csv' % (assay, z)) for d in dpdirs]
            if not op.exists(f1):
                continue
            diffs, dkyub = diff(f0, f1)
            out = []
            for ch in dkyub.readouts:
                m = max(dkyub.get_column(ch))
                if str(m) != '0.0' and m > 1e-6:
                    out.append((u'%s: %s' % (ch, str(m))).encode('utf-8'))

            expected = expected_template[z] % locals()
            if diffs != expected:
                lcp = op.commonprefix(diffs, expected)
                lls = lc, la, lb = map(len, (lcp, diffs, expected))
                ST()
                sfxs = [s[lc:] if len(s) > lc else None for s in (diffs, expected)]
                ST()
                print sfxs
            if out:
                print '%s %s' % (assay, z)
                print '\n'.join(out)
                print
        #exit(0)

if __name__ == '__main__':
    from glob import glob
    import os.path as op
    def _getkyub(path):
        return Kyub(*datapflex.read_datapflex(path))

#     irdir = '/home/gfb2/IR'
#     dpdir = op.join(irdir, 'DATAPFLEX_111018T')
    import sys
    dpdir = sys.argv[1]
    outpath = op.join(dpdir, 'ALL.csv')

    ks = map(_getkyub,
             [p for p in [op.join(dpdir, '%s_%s.csv' % (op.basename(sp), z))
                          for sp in sorted(glob('scans/linkfarm/*'))
                          for z in ('GF', 'CK')]
              if op.exists(p) and p != outpath])

    k = Kyub.merge(*ks)
    def _mkTC(hu):
        p = hu.split('=')
        h = p[0]
        u = p[1] if len(p) > 1 else None
        return Column(h, iterable=k.get_treatment_column(hu), units=u)

    def _mkDC(h):
        return Column(h, iterable=k.get_column(h))

#     def _mkDC(h):
#         m = k.get_column(h)
#         s = k.get_column(h + '=stdev')
#         return MSColumn(h, iterable=zip(m, s))

    tc = [_mkTC(f) for f in k.factors]
    dc = [_mkDC(f) for f in k.readouts]
    #dc = [_mkDC(f) for f in k.readouts if not f.endswith('=stdev')]

    datapflex.write_datapflex(outpath, tc, dc)

#     for p in sorted(glob('scans/linkfarm/*')):
#         assay = op.basename(p)
#         for z in ('GF', 'CK'):
#             f0, f1 = fs = [op.join(d, '%s_%s.csv' % (assay, z)) for d in dpdirs]
#             if not op.exists(f1):
#                 continue
#             diffs, dkyub = diff(f0, f1)
#             out = []
