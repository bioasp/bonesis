
from zipfile import ZipFile
import os
import tempfile

from boolean import boolean
from colomoto import minibn
from colomoto_jupyter import import_colomoto_tool
from numpy.random import choice
import networkx as nx
import pandas as pd

class BonesisDomain(object):
    pass

def formula_well_formed(ba, f):
    pos_lits = set()
    neg_lits = set()
    def is_lit(f):
        if isinstance(f, ba.Symbol):
            pos_lits.add(f.obj)
            return True
        if isinstance(f, ba.NOT) \
                and isinstance(f.args[0], ba.Symbol):
            neg_lits.add(f.args[0].obj)
            return True
        return False

    def is_clause(f):
        if is_lit(f):
            return True
        if isinstance(f, ba.AND):
            for g in f.args:
                if not is_lit(g):
                    return False
            return True
        return False

    def test_monotonicity():
        both = pos_lits.intersection(neg_lits)
        return not both

    if f in [ba.TRUE, ba.FALSE]:
        return True
    if is_clause(f):
        return test_monotonicity()
    if isinstance(f, ba.OR):
        for g in f.args:
            if not is_clause(g):
                return False
        return test_monotonicity()
    return False

class BooleanNetwork(BonesisDomain, minibn.BooleanNetwork):
    def __init__(self, bn):
        if isinstance(bn, str):
            if "\n" in bn or not os.path.exists(bn):
                bn = minibn.BooleanNetwork(bn)
            else:
                bn = minibn.BooleanNetwork.load(bn)
        elif isinstance(bn, dict):
            bn = minibn.BooleanNetwork(bn)
        assert isinstance(bn, minibn.BooleanNetwork)
        super().__init__()
        self.ba = bn.ba
        for n, f in bn.items():
            self[n] = f

    @classmethod
    def load(celf, *args, **kwargs):
        return celf(minibn.BooleanNetwork.load(*args, **kwargs))

    def __setitem__(self, n, f):
        f = self.ba.dnf(f).simplify()
        assert formula_well_formed(self.ba, f), f"'{f}' for {n} does not look monotone.."
        super().__setitem__(n, f)


class BooleanNetworksEnsemble(BonesisDomain, list):
    def __init__(self, bns=None):
        super().__init__(bns if bns is not None else [])

    @classmethod
    def from_zip(celf, zipfile, ensure_wellformed=False):
        bns = celf()
        make_bn = BooleanNetwork if ensure_wellformed else minibn.BooleanNetwork
        with ZipFile(zipfile, "r") as bundle:
            for entry in bundle.infolist():
                if entry.is_dir() or not \
                        entry.filename.lower().endswith(".bnet"):
                    continue
                with bundle.open(entry) as fp:
                    bns.append(make_bn(fp.read().decode()))
        return bns



label_map = {
    1: "+",
    -1: "-",
    0: "?"
}
sign_map = {
    1: 1,
    -1: -1,
    "->": 1,
    "-|": -1,
    "+": 1,
    "-": -1,
    "+1": 1,
    "-1": -1,
    "ukn": 0,
    "?": 0,
    "unspecified": 0,
}
def sign_of_label(label):
    if label in sign_map:
        return sign_map[label]
    label = label.lower()
    if label.startswith("act") or label.startswith("stim"):
        return 1
    if label.startswith("inh"):
        return -1
    raise ValueError(label)

class InfluenceGraph(BonesisDomain, nx.MultiDiGraph):
    _options = (
        "allow_skipping_nodes",
        "canonic",
        "exact",
        "maxclause",
    )
    def __init__(self, graph=None,
            maxclause=None,
            allow_skipping_nodes=False,
            canonic=True,
            exact=False,
            autolabel=True):
        nx.MultiDiGraph.__init__(self, graph)
        # TODO: ensures graph is well-formed
        self.maxclause = maxclause
        self.allow_skipping_nodes = allow_skipping_nodes
        self.canonic = canonic
        self.exact = exact
        if autolabel:
            for a, b, data in self.edges(data=True):
                if "label" not in data:
                    l = label_map.get(data.get("sign"))
                    if l:
                        data["label"] = l

    def sources(self):
        return set([n for n,i in self.in_degree(self.nodes()) if i == 0])
    def unsource(self):
        self.add_edges_from([(n, n, {"sign": 1, "label": "+"}) for n in self.sources()])

    def max_indegree(self):
        return max(dict(self.in_degree()).values())

    @property
    def options(self):
        return {opt: getattr(self, opt) for opt in self._options}

    def subgraph(self, *args, **kwargs):
        g = super().subgraph(*args, **kwargs)
        for opt in self._options:
            setattr(g, opt, getattr(self, opt))
        return g

    @classmethod
    def from_csv(celf, filename, column_source=0, column_target=1, column_sign=2,
                    sep=",",
                    unsource=True, **kwargs):
        df = pd.read_csv(filename, sep=sep)
        def get_colname(spec):
            return df.columns[spec] if isinstance(spec, int) else spec
        column_source = get_colname(column_source)
        column_target = get_colname(column_target)
        column_sign = get_colname(column_sign)
        df.rename(columns = {
            column_source: "in",
            column_target: "out",
            column_sign: "sign"}, inplace=True)
        df["sign"] = df["sign"].map(sign_of_label)
        g = nx.from_pandas_edgelist(df, "in", "out", ["sign"], nx.MultiDiGraph())
        pkn = celf(g, **kwargs)
        if unsource:
            pkn.unsource()
        return pkn

    @classmethod
    def from_sif(celf, filename, sep="\\s+", unsource=True, **kwargs):
        df = pd.read_csv(filename, header=None,
                names=("in", "sign", "out"), sep=sep)
        df["sign"] = df["sign"].map(sign_of_label)
        g = nx.from_pandas_edgelist(df, "in", "out", ["sign"], nx.MultiDiGraph())
        pkn = celf(g, **kwargs)
        if unsource:
            pkn.unsource()
        return pkn

    @classmethod
    def from_ginsim(celf, lrg, **kwargs):
        ginsim = import_colomoto_tool("ginsim")
        fd, filename = tempfile.mkstemp(".sif")
        os.close(fd)
        try:
            ginsim.service("reggraph").export(lrg, filename)
            pkn = celf.from_sif(filename, **kwargs)
        finally:
            os.unlink(filename)
        return pkn

    @classmethod
    def complete(celf, n, sign=0, loops=True, **kwargs):
        g = nx.complete_graph(n, nx.DiGraph)
        for e in g.edges(data=True):
            e[2]["sign"] = sign
        if loops:
            for i in g:
                g.add_edge(i, i, sign=sign)
        return celf(g, **kwargs)

    @classmethod
    def all_on_one(celf, n, sign=1, **kwargs):
        g = nx.DiGraph()
        for i in range(n):
            g.add_edge(i, 0, sign=sign)
        return celf(g, **kwargs)

    @classmethod
    def scale_free(celf, n, p_pos=0.6, unsource=True, **kwargs):
        scale_free_kwargs = dict([(k,v) for (k,v) in kwargs.items() \
                if k not in celf._options])
        celf_kwargs = dict([(k,v) for (k,v) in kwargs.items() \
                if k in celf._options])
        g = nx.DiGraph(nx.scale_free_graph(n, **scale_free_kwargs))
        signs = choice([-1,1], size=len(g.edges()), p=[1-p_pos,p_pos])
        for j, e in enumerate(g.edges(data=True)):
            e[2]["sign"] = signs[j]
        pkn = celf(g, **celf_kwargs)
        if unsource:
            pkn.unsource()
        return pkn
