# scripts/inspect_chroma.py
import os
import sys
import chromadb

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import get_settings

def main():
    settings = get_settings()
    db_path = settings.CHROMA_PATH
    print(f"Connecting to Chroma database at: {db_path}...")
    
    if not os.path.exists(db_path):
        print(f"Error: Database path '{db_path}' does not exist.")
        return

    try:
        client = chromadb.PersistentClient(path=db_path)
        collections = client.list_collections()
        print(f"\nFound {len(collections)} collection(s):")
        for col in collections:
            count = col.count()
            print(f" - Collection: '{col.name}' | Total Chunks: {count}")
            if count > 0:
                print("   Previewing first 2 chunks:")
                results = col.peek(limit=2)
                for i in range(len(results["ids"])):
                    chunk_id = results["ids"][i]
                    document = results["documents"][i][:120] + "..."
                    meta = results["metadatas"][i]
                    print(f"     * [{chunk_id}] (Paper: {meta.get('paper_id')}): {document}")
    except Exception as e:
        print(f"Error inspecting Chroma DB: {e}")

if __name__ == "__main__":
    main()
