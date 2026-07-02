import chromadb
client = chromadb.PersistentClient(path="chroma")
coll = client.get_collection("email_chunks")
print(f"Total chunks: {coll.count():,}")

# Sanity: a Topic 204-flavoured query should return actually-relevant hits
results = coll.query(
    query_texts=["document retention deletion shredding preservation"],
    n_results=5,
)
for i, (doc_id, snippet, dist) in enumerate(zip(
    results["metadatas"][0], results["documents"][0], results["distances"][0]
)):
    print(f"\n#{i+1} distance={dist:.3f}  doc={doc_id['doc_id']}")
    print(f"  {snippet[:250]}...")