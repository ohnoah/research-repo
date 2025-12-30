"""
Django Ninja API endpoints for SQLAlchemy/pgvector operations.

Demonstrates:
- Direct SQLAlchemy access alongside Django ORM
- pgvector similarity search operations
- Prepared statement handling through PgBouncer
"""

import time
import random
from typing import Optional

from ninja import Router, Schema
from pydantic import Field

from .sqlalchemy_models import (
    VectorDocument,
    VectorSearchResult,
    direct_session_scope,
    pooled_session_scope,
    cosine_similarity_search,
    l2_distance_search,
    create_tables,
)

router = Router()


# =============================================================================
# Schemas
# =============================================================================

class DocumentCreate(Schema):
    title: str
    content: str
    metadata: dict = Field(default_factory=dict)
    embedding: Optional[list[float]] = None


class DocumentOut(Schema):
    id: int
    title: str
    content: str
    metadata: dict
    has_embedding: bool


class SimilaritySearchRequest(Schema):
    query_embedding: list[float]
    limit: int = 10
    use_pooled: bool = True


class SearchResultOut(Schema):
    document_id: int
    title: str
    content_preview: str
    similarity_score: float


class PreparedStatementTestResult(Schema):
    iterations: int
    connection_type: str
    avg_query_time_ms: float
    prepared_statements_used: bool
    notes: str


# =============================================================================
# Document CRUD Endpoints
# =============================================================================

@router.post("/documents", response=DocumentOut)
def create_document(request, payload: DocumentCreate):
    """Create a new document with optional embedding."""
    with pooled_session_scope() as session:
        doc = VectorDocument(
            title=payload.title,
            content=payload.content,
            doc_metadata=payload.metadata,
            embedding=payload.embedding,
        )
        session.add(doc)
        session.flush()  # Get the ID

        return {
            'id': doc.id,
            'title': doc.title,
            'content': doc.content,
            'metadata': doc.doc_metadata or {},
            'has_embedding': doc.embedding is not None,
        }


@router.get("/documents", response=list[DocumentOut])
def list_documents(request, limit: int = 100, use_pooled: bool = True):
    """List documents using specified connection type."""
    session_scope = pooled_session_scope if use_pooled else direct_session_scope

    with session_scope() as session:
        docs = session.query(VectorDocument).limit(limit).all()
        return [
            {
                'id': doc.id,
                'title': doc.title,
                'content': doc.content,
                'metadata': doc.doc_metadata or {},
                'has_embedding': doc.embedding is not None,
            }
            for doc in docs
        ]


@router.get("/documents/{doc_id}", response=DocumentOut)
def get_document(request, doc_id: int):
    """Get a single document by ID."""
    with pooled_session_scope() as session:
        doc = session.query(VectorDocument).get(doc_id)
        if not doc:
            return {"error": "Document not found"}, 404
        return {
            'id': doc.id,
            'title': doc.title,
            'content': doc.content,
            'metadata': doc.doc_metadata or {},
            'has_embedding': doc.embedding is not None,
        }


@router.post("/documents/{doc_id}/embedding")
def set_document_embedding(request, doc_id: int, embedding: list[float]):
    """Set or update the embedding for a document."""
    with pooled_session_scope() as session:
        doc = session.query(VectorDocument).get(doc_id)
        if not doc:
            return {"error": "Document not found"}, 404

        doc.embedding = embedding
        session.commit()

        return {"success": True, "document_id": doc_id}


# =============================================================================
# Vector Search Endpoints
# =============================================================================

@router.post("/search/cosine", response=list[SearchResultOut])
def search_cosine_similarity(request, payload: SimilaritySearchRequest):
    """
    Search documents by cosine similarity.

    This uses pgvector's cosine_distance operator for efficient similarity search.
    """
    session_scope = pooled_session_scope if payload.use_pooled else direct_session_scope

    with session_scope() as session:
        results = cosine_similarity_search(
            session,
            payload.query_embedding,
            limit=payload.limit
        )

        return [
            {
                'document_id': doc.id,
                'title': doc.title,
                'content_preview': doc.content[:200] + '...' if len(doc.content) > 200 else doc.content,
                'similarity_score': float(score),
            }
            for doc, score in results
        ]


@router.post("/search/l2", response=list[SearchResultOut])
def search_l2_distance(request, payload: SimilaritySearchRequest):
    """
    Search documents by L2 (Euclidean) distance.

    Lower distance = more similar.
    """
    session_scope = pooled_session_scope if payload.use_pooled else direct_session_scope

    with session_scope() as session:
        results = l2_distance_search(
            session,
            payload.query_embedding,
            limit=payload.limit
        )

        return [
            {
                'document_id': doc.id,
                'title': doc.title,
                'content_preview': doc.content[:200] + '...' if len(doc.content) > 200 else doc.content,
                'similarity_score': float(1 / (1 + distance)),  # Convert distance to similarity
            }
            for doc, distance in results
        ]


# =============================================================================
# Prepared Statement Testing
# =============================================================================

@router.get("/test/prepared-statements", response=PreparedStatementTestResult)
def test_prepared_statements(request, iterations: int = 100, use_pooled: bool = True):
    """
    Test prepared statement behavior.

    This endpoint runs the same query multiple times to observe prepared
    statement caching behavior. With psycopg3's prepare_threshold,
    queries get prepared after N executions.

    Through PgBouncer:
    - Requires max_prepared_statements > 0 in PgBouncer config
    - PgBouncer tracks prepared statements per connection
    """
    session_scope = pooled_session_scope if use_pooled else direct_session_scope

    times = []

    with session_scope() as session:
        # First, ensure we have some data
        if session.query(VectorDocument).count() == 0:
            # Create sample documents
            for i in range(10):
                doc = VectorDocument(
                    title=f"Sample Document {i}",
                    content=f"This is sample content for document {i}.",
                    embedding=[random.random() for _ in range(384)]
                )
                session.add(doc)
            session.commit()

        # Run the same query multiple times
        for i in range(iterations):
            start = time.perf_counter()
            # Simple query that should benefit from prepared statements
            session.query(VectorDocument).filter(
                VectorDocument.id > 0
            ).limit(10).all()
            end = time.perf_counter()
            times.append((end - start) * 1000)  # Convert to ms

    avg_time = sum(times) / len(times)

    # First few queries are typically slower (parsing/planning)
    # Later queries should be faster if prepared statements are working
    first_5_avg = sum(times[:5]) / 5 if len(times) >= 5 else avg_time
    last_5_avg = sum(times[-5:]) / 5 if len(times) >= 5 else avg_time

    notes = (
        f"First 5 queries avg: {first_5_avg:.3f}ms, Last 5 queries avg: {last_5_avg:.3f}ms. "
        f"Speedup from prepared statements: {first_5_avg / last_5_avg:.2f}x. "
        f"Connection type: {'pooled (PgBouncer)' if use_pooled else 'direct'}."
    )

    return {
        'iterations': iterations,
        'connection_type': 'pooled' if use_pooled else 'direct',
        'avg_query_time_ms': avg_time,
        'prepared_statements_used': first_5_avg > last_5_avg * 1.1,  # >10% speedup
        'notes': notes,
    }


@router.get("/test/connection-reuse")
def test_connection_reuse(request, queries: int = 10, use_pooled: bool = True):
    """
    Test connection reuse behavior.

    Shows how connections are reused across queries within
    and outside of transactions.
    """
    session_scope = pooled_session_scope if use_pooled else direct_session_scope
    pids = []

    from sqlalchemy import text

    with session_scope() as session:
        for _ in range(queries):
            result = session.execute(
                text("SELECT pg_backend_pid()")
            ).scalar()
            pids.append(result)

    unique_pids = len(set(pids))

    return {
        'queries': queries,
        'connection_type': 'pooled' if use_pooled else 'direct',
        'backend_pids': pids,
        'unique_pids': unique_pids,
        'notes': (
            f"Within a session, all queries used {'the same' if unique_pids == 1 else 'different'} "
            f"backend connection(s). With PgBouncer transaction pooling, the same server "
            f"connection is used for the duration of the transaction/session."
        )
    }


# =============================================================================
# Setup Endpoints
# =============================================================================

@router.post("/setup/create-tables")
def setup_create_tables(request):
    """Create SQLAlchemy tables (uses direct connection)."""
    try:
        create_tables()
        return {"success": True, "message": "Tables created successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/setup/seed-data")
def seed_sample_data(request, count: int = 50):
    """
    Seed the database with sample documents and embeddings.

    Uses pooled connection to test bulk inserts through PgBouncer.
    """
    with pooled_session_scope() as session:
        for i in range(count):
            doc = VectorDocument(
                title=f"Document {i}: {random.choice(['Tech', 'Science', 'Art', 'History'])}",
                content=f"This is the content of document {i}. It contains various "
                        f"information about {random.choice(['programming', 'physics', 'painting', 'ancient civilizations'])}.",
                doc_metadata={'category': random.choice(['tech', 'science', 'art', 'history'])},
                # Generate random 384-dimensional embedding
                embedding=[random.gauss(0, 1) for _ in range(384)]
            )
            session.add(doc)

        session.commit()

    return {"success": True, "documents_created": count}
