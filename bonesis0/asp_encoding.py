
import clingo as asp

from scipy.special import binom

from functools import reduce

def string_of_facts(facts):
    if not facts:
        return ""
    return "{}.".format(".\n".join(map(str,facts)))

def print_facts(facts):
    if facts:
        print(string_of_facts(facts))

def nb_clauses(d):
    return int(binom(d, d//2))

def pkn_to_facts(pkn, maxclause=None, allow_skipping_nodes=False):
    facts = []
    if not allow_skipping_nodes:
        facts.append(asp.Function("nbnode", [asp.Number(len(pkn.nodes()))]))
        for n in pkn.nodes():
            facts.append(asp.Function("node", [asp.String(n)]))
    else:
        facts.append("nbnode(NB) :- NB = #count{N: node(N)}")
        for n in pkn.nodes():
            facts.append("{{{}}}".format(asp.Function("node", [asp.String(n)])))
    for (orig, dest, data) in pkn.edges(data=True):
        if data["sign"] in ["ukn","?"]:
            f = "in({},{},(-1;1))".format(asp.String(orig), asp.String(dest))
            facts.append(f)
        else:
            s = asp.Number(int(data["sign"]))
            facts.append(asp.Function("in",
                [asp.String(orig), asp.String(dest), s]))
    def bounded_nb_clauses(d):
        nbc = nb_clauses(d)
        if maxclause:
            nbc = min(maxclause, nbc)
        return nbc
    for n, i in pkn.in_degree(pkn.nodes()):
        facts.append(asp.Function("maxC", [asp.String(n),
            asp.Number(bounded_nb_clauses(i))]))
    return facts

def obs_to_facts(pstate, obsid):
    return [asp.Function("obs", [obsid, n, 2*v-1]) for (n,v) in pstate.items()]

def dnfs_of_facts(fs):
    bn = {}
    for d in fs:
        if d.name == "clause":
            (i,cid,lit,sign) = d.arguments
            i = i.string
            cid = cid.number
            sign = sign.number
            lit = lit.string
            if i not in bn:
                bn[i] = []
            if cid > len(bn[i]):
                bn[i] += [set() for j in range(cid-len(bn[i]))]
            bn[i][cid-1].add((sign,lit))
        elif d.name == "constant" and len(d.arguments) == 2:
            (i,v) = d.arguments
            i = i.string
            v = v.number
            bn[i] = v == 1
    return bn

from colomoto.minibn import BooleanNetwork
def minibn_of_facts(fs):
    dnfs = dnfs_of_facts(fs)
    bn = BooleanNetwork()
    def make_lit(l):
        s,v=l
        v = bn.v(v)
        if s < 0:
            v = ~v
        return v
    def make_clause(ls):
        return reduce(lambda l1,l2: l1&l2, map(make_lit, ls))
    def make_dnf(cs):
        if isinstance(cs, bool):
            return cs
        cs = filter(len, cs)
        return reduce(lambda c1, c2: c1|c2, map(make_clause, cs))
    for (node, cs) in sorted(dnfs.items()):
        bn[node] = make_dnf(cs)
    return bn

