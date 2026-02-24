"""
Simple RAG (Retrieval-Augmented Generation) Engine
Uses keyword matching for prototype - no vector embeddings needed
"""
import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path


class SimpleRAG:
    """
    Naive RAG implementation using keyword matching
    Perfect for prototypes with <100 documents
    """
    
    def __init__(self, knowledge_base_path: str = "knowledge_base"):
        self.kb_path = Path(knowledge_base_path)
        self.documents: List[Dict[str, Any]] = []
        self.load_knowledge_base()
    
    def load_knowledge_base(self):
        """Load all JSON files from knowledge base directory"""
        if not self.kb_path.exists():
            print(f"Warning: Knowledge base path {self.kb_path} does not exist")
            return
        
        for json_file in self.kb_path.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Handle both list and dict formats
                    if isinstance(data, list):
                        self.documents.extend(data)
                    elif isinstance(data, dict):
                        # If dict has a 'data' or 'items' key, use that
                        if 'data' in data:
                            self.documents.extend(data['data'])
                        elif 'items' in data:
                            self.documents.extend(data['items'])
                        else:
                            self.documents.append(data)
                
                print(f"Loaded {json_file.name}")
            except Exception as e:
                print(f"Error loading {json_file}: {e}")
        
        print(f"Total documents loaded: {len(self.documents)}")
    
    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve most relevant documents using keyword matching
        
        Args:
            query: Search query
            top_k: Number of documents to return
            filters: Optional filters (e.g., {"category": "beach"})
        
        Returns:
            List of relevant documents with scores
        """
        query_words = set(query.lower().split())
        scored_docs = []
        
        for doc in self.documents:
            # Apply filters if provided
            if filters:
                if not all(doc.get(k) == v for k, v in filters.items()):
                    continue
            
            # Calculate relevance score
            score = self._calculate_score(doc, query_words)
            
            if score > 0:
                scored_docs.append({
                    "document": doc,
                    "score": score
                })
        
        # Sort by score and return top_k
        scored_docs.sort(key=lambda x: x["score"], reverse=True)
        return scored_docs[:top_k]
    
    def _calculate_score(self, doc: Dict[str, Any], query_words: set) -> float:
        """Calculate relevance score for a document"""
        score = 0.0
        
        # Searchable fields with weights
        field_weights = {
            "name": 3.0,
            "title": 3.0,
            "category": 2.5,
            "tags": 2.0,
            "description": 1.0,
            "content": 1.0,
            "tips": 1.0,
        }
        
        for field, weight in field_weights.items():
            if field in doc:
                field_value = str(doc[field]).lower()
                field_words = set(field_value.split())
                
                # Count matching words
                matches = len(query_words & field_words)
                score += matches * weight
        
        return score
    
    def format_context(
        self,
        retrieved_docs: List[Dict[str, Any]],
        max_length: Optional[int] = None
    ) -> str:
        """
        Format retrieved documents into context string for LLM
        
        Args:
            retrieved_docs: List of documents from retrieve()
            max_length: Optional max character length
        
        Returns:
            Formatted context string
        """
        context_parts = []
        
        for i, item in enumerate(retrieved_docs, 1):
            doc = item["document"]
            score = item["score"]
            
            # Format document
            doc_text = f"[Document {i}] (Relevance: {score:.1f})\n"
            
            # Add key fields
            if "name" in doc:
                doc_text += f"Name: {doc['name']}\n"
            if "category" in doc:
                doc_text += f"Category: {doc['category']}\n"
            if "description" in doc:
                doc_text += f"Description: {doc['description']}\n"
            if "distance" in doc:
                doc_text += f"Distance: {doc['distance']}\n"
            if "cost" in doc:
                doc_text += f"Cost: {doc['cost']}\n"
            if "best_time" in doc:
                doc_text += f"Best Time: {doc['best_time']}\n"
            if "tips" in doc:
                doc_text += f"Tips: {doc['tips']}\n"
            
            context_parts.append(doc_text)
        
        context = "\n---\n".join(context_parts)
        
        # Truncate if needed
        if max_length and len(context) > max_length:
            context = context[:max_length] + "\n... (truncated)"
        
        return context
    
    def search(
        self,
        query: str,
        top_k: int = 3,
        filters: Optional[Dict[str, Any]] = None,
        format_for_llm: bool = True
    ) -> str:
        """
        One-step search and format for LLM
        
        Args:
            query: Search query
            top_k: Number of results
            filters: Optional filters
            format_for_llm: Whether to format as context string
        
        Returns:
            Formatted context string or raw results
        """
        results = self.retrieve(query, top_k, filters)
        
        if format_for_llm:
            return self.format_context(results)
        else:
            return results


# Convenience function
def quick_search(query: str, top_k: int = 3) -> str:
    """Quick search without managing RAG instance"""
    rag = SimpleRAG()
    return rag.search(query, top_k)


# Example usage
if __name__ == "__main__":
    # Test the RAG engine
    rag = SimpleRAG()
    
    # Search for beaches
    print("=== Searching for beaches ===")
    context = rag.search("beach weekend trip", top_k=2)
    print(context)
    
    print("\n=== Searching for treks ===")
    context = rag.search("trekking adventure", top_k=2)
    print(context)
    
    # Search with filters
    print("\n=== Searching with category filter ===")
    results = rag.retrieve("weekend trip", top_k=3, filters={"category": "beach"})
    for result in results:
        print(f"Score: {result['score']}, Name: {result['document'].get('name')}")
