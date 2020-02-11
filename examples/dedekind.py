
import sys

import bonesis

n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
dom = bonesis.InfluenceGraph.all_on_one(n)

bo = bonesis.BoNesis(dom)

for i in range(1,n):
    bo.constant(i, False)

bns = bo.boolean_networks()
print(bns.standalone())
print(bns.count())


