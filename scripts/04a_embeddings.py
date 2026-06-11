"""P4 step 4a: node2vec embeddings (train-only AND full-data leak variant).

ENVIRONMENT CAVEAT (documented, deliberate): gensim 4.4.0 pins numpy<2, which
conflicts with this machine's numpy 2.4.4 (needed by rasterio/opencv in other
projects). Protocol: gensim is installed temporarily, THIS script runs once and
saves embeddings to CSV, then the environment is restored (numpy 2.4.4, gensim
removed). 04_model.py consumes only the CSVs. Cold reproduction of THIS script
requires: pip install node2vec gensim; run; pip uninstall; reinstall numpy.

node2vec parameterization: p = q = 1 (the node2vec default - uniform second-
order walks, equivalent to DeepWalk), directed out-edge walks. Embeddings via
gensim Word2Vec skip-gram (API smoke-tested + verified this session).
Determinism: seed=42 everywhere, workers=1, run with PYTHONHASHSEED=0.

  walks: 10 per start node, length 20 | Word2Vec: dim=32, window=5, sg=1,
  epochs=5, min_count=1

Run:  $env:PYTHONHASHSEED='0'; python scripts/04a_embeddings.py
Outputs: data/clean/emb_train.csv, data/clean/emb_full.csv
"""

import os

import numpy as np
import pandas as pd
from gensim.models import Word2Vec

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
CLEAN = os.path.join(PROJ, "data", "clean")

SEED = 42
NUM_WALKS = 10
WALK_LEN = 20
DIM = 32

legs = pd.read_csv(os.path.join(CLEAN, "legs.csv"))


def out_adjacency(frame):
    adj = {}
    for s, d in frame[["source_center", "destination_center"]].drop_duplicates().values:
        adj.setdefault(s, []).append(d)
    nodes = set(adj) | set(frame["destination_center"])
    return adj, sorted(nodes)


def walks_for(adj, nodes, rng):
    walks = []
    for _ in range(NUM_WALKS):
        for start in nodes:
            walk = [start]
            cur = start
            for _ in range(WALK_LEN - 1):
                nxt = adj.get(cur)
                if not nxt:
                    break  # sink node: walk ends
                cur = nxt[rng.integers(0, len(nxt))]
                walk.append(cur)
            walks.append(walk)
    return walks


def embed(frame, tag):
    adj, nodes = out_adjacency(frame)
    rng = np.random.default_rng(SEED)
    walks = walks_for(adj, nodes, rng)
    model = Word2Vec(walks, vector_size=DIM, window=5, min_count=1, sg=1,
                     epochs=5, seed=SEED, workers=1)
    emb = pd.DataFrame({"center": nodes})
    vecs = np.vstack([model.wv[n] for n in nodes])
    for i in range(DIM):
        emb[f"e{i}"] = vecs[:, i]
    path = os.path.join(CLEAN, f"emb_{tag}.csv")
    emb.to_csv(path, index=False)
    print(f"[{tag}] {len(nodes)} nodes embedded, {len(walks)} walks "
          f"(mean len {np.mean([len(w) for w in walks]):.1f}) -> {path}")
    return set(nodes)


train_nodes = embed(legs[legs["data"] == "training"], "train")
full_nodes = embed(legs, "full")
print(f"[check] nodes only in full (test-period cold-start): "
      f"{len(full_nodes - train_nodes)}")
