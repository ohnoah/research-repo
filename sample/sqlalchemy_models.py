"""
SQLAlchemy models with pgvector support.

This module provides direct SQLAlchemy access to PostgreSQL with pgvector,
bypassing Django ORM for advanced vector operations.

Key features:
- Sync and async engine support
- pgvector Vector type for similarity search
- Prepared statement handling
"""

import os
from typing import Optional
from contextlib import contextmanager

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    relationship,
    Session,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from pgvector.sqlalchemy import Vector

# =============================================================================
# Database Configuration
# =============================================================================

def get_database_url(use_pooled: bool = False) -> str:
    """
    Get the database URL for SQLAlchemy.

    Args:
        use_pooled: If True, connect via PgBouncer. If False, direct connection.
    """
    db_name = os.environ.get('DB_NAME', 'myapp_db')
    db_user = os.environ.get('DB_USER', 'myapp_user')
    db_password = os.environ.get('DB_PASSWORD', 'myapp_password')

    if use_pooled:
        db_host = os.environ.get('DB_HOST_POOLED', 'localhost')
        db_port = os.environ.get('DB_PORT_POOLED', '6432')
    else:
        db_host = os.environ.get('DB_HOST', 'localhost')
        db_port = os.environ.get('DB_PORT', '5432')

    return f"postgresql+psycopg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


# =============================================================================
# Engine Configuration
# =============================================================================

def create_direct_engine():
    """
    Create a SQLAlchemy engine for direct PostgreSQL connection.

    This is used for:
    - Migrations and schema operations
    - Long-running queries
    - Operations requiring server-side cursors
    """
    return create_engine(
        get_database_url(use_pooled=False),
        echo=os.environ.get('DEBUG', 'false').lower() == 'true',
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Health check connections
        # Prepared statements work fine on direct connections
        connect_args={
            'prepare_threshold': 5,  # Prepare statements after 5 uses
        }
    )


def create_pooled_engine():
    """
    Create a SQLAlchemy engine for PgBouncer connection.

    Important: PgBouncer in transaction mode requires special handling
    for prepared statements.
    """
    return create_engine(
        get_database_url(use_pooled=True),
        echo=os.environ.get('DEBUG', 'false').lower() == 'true',
        pool_size=10,  # Can be higher since PgBouncer handles pooling
        max_overflow=20,
        pool_pre_ping=True,
        connect_args={
            # For PgBouncer transaction pooling, we need to handle
            # prepared statements carefully. Options:
            # 1. Disable prepared statements entirely (prepare_threshold=0)
            # 2. Use PgBouncer's max_prepared_statements feature
            # We'll use option 2 since our PgBouncer is configured with
            # MAX_PREPARED_STATEMENTS=100
            'prepare_threshold': 5,
        }
    )


# =============================================================================
# Session Factories
# =============================================================================

# Lazy initialization of engines and sessions
_direct_engine = None
_pooled_engine = None
_DirectSession = None
_PooledSession = None


def get_direct_session() -> Session:
    """Get a session using direct PostgreSQL connection."""
    global _direct_engine, _DirectSession
    if _direct_engine is None:
        _direct_engine = create_direct_engine()
        _DirectSession = sessionmaker(bind=_direct_engine)
    return _DirectSession()


def get_pooled_session() -> Session:
    """Get a session using PgBouncer connection."""
    global _pooled_engine, _PooledSession
    if _pooled_engine is None:
        _pooled_engine = create_pooled_engine()
        _PooledSession = sessionmaker(bind=_pooled_engine)
    return _PooledSession()


@contextmanager
def direct_session_scope():
    """Context manager for direct database sessions."""
    session = get_direct_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def pooled_session_scope():
    """Context manager for pooled database sessions."""
    session = get_pooled_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# =============================================================================
# SQLAlchemy Models
# =============================================================================

Base = declarative_base()


class VectorDocument(Base):
    """
    A document with vector embeddings for similarity search.

    This model uses pgvector's Vector type for efficient similarity operations.
    """
    __tablename__ = 'vector_documents'

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    doc_metadata = Column(JSONB, default={})

    # Vector embedding using pgvector
    # 384 dimensions is common for sentence-transformers models
    embedding = Column(Vector(384), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Create an index for vector similarity search
    __table_args__ = (
        # IVFFlat index for approximate nearest neighbor search
        # Lists parameter should be sqrt(rows) for optimal performance
        Index(
            'ix_vector_documents_embedding',
            embedding,
            postgresql_using='ivfflat',
            postgresql_with={'lists': 100},
            postgresql_ops={'embedding': 'vector_cosine_ops'}
        ),
    )

    def __repr__(self):
        return f"<VectorDocument(id={self.id}, title='{self.title}')>"


class VectorSearchResult(Base):
    """
    A table to store search results for analysis.

    Useful for testing prepared statement behavior and connection pooling.
    """
    __tablename__ = 'vector_search_results'

    id = Column(Integer, primary_key=True)
    query_text = Column(Text, nullable=False)
    document_id = Column(Integer, ForeignKey('vector_documents.id'))
    similarity_score = Column(Float)
    connection_type = Column(String(20))  # 'direct' or 'pooled'
    search_time_ms = Column(Float)
    created_at = Column(DateTime, server_default=func.now())

    document = relationship("VectorDocument", backref="search_results")

    def __repr__(self):
        return f"<VectorSearchResult(query='{self.query_text[:20]}...', score={self.similarity_score})>"


# =============================================================================
# Vector Operations
# =============================================================================

def create_tables():
    """Create all SQLAlchemy tables using direct connection."""
    engine = create_direct_engine()
    Base.metadata.create_all(engine)
    print("SQLAlchemy tables created successfully.")


def drop_tables():
    """Drop all SQLAlchemy tables using direct connection."""
    engine = create_direct_engine()
    Base.metadata.drop_all(engine)
    print("SQLAlchemy tables dropped.")


def cosine_similarity_search(
    session: Session,
    query_embedding: list[float],
    limit: int = 10
) -> list[tuple[VectorDocument, float]]:
    """
    Perform cosine similarity search using pgvector.

    Args:
        session: SQLAlchemy session
        query_embedding: Query vector (384 dimensions)
        limit: Maximum number of results

    Returns:
        List of (document, similarity_score) tuples
    """
    from sqlalchemy import select

    # pgvector cosine distance: 1 - cosine_similarity
    # So we order by distance ASC and return 1 - distance as similarity
    query = (
        select(
            VectorDocument,
            (1 - VectorDocument.embedding.cosine_distance(query_embedding)).label('similarity')
        )
        .where(VectorDocument.embedding.isnot(None))
        .order_by(VectorDocument.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )

    results = session.execute(query).all()
    return [(row[0], row[1]) for row in results]


def l2_distance_search(
    session: Session,
    query_embedding: list[float],
    limit: int = 10
) -> list[tuple[VectorDocument, float]]:
    """
    Perform L2 (Euclidean) distance search using pgvector.

    Args:
        session: SQLAlchemy session
        query_embedding: Query vector (384 dimensions)
        limit: Maximum number of results

    Returns:
        List of (document, distance) tuples (lower is more similar)
    """
    from sqlalchemy import select

    query = (
        select(
            VectorDocument,
            VectorDocument.embedding.l2_distance(query_embedding).label('distance')
        )
        .where(VectorDocument.embedding.isnot(None))
        .order_by(VectorDocument.embedding.l2_distance(query_embedding))
        .limit(limit)
    )

    results = session.execute(query).all()
    return [(row[0], row[1]) for row in results]


def inner_product_search(
    session: Session,
    query_embedding: list[float],
    limit: int = 10
) -> list[tuple[VectorDocument, float]]:
    """
    Perform inner product (dot product) search using pgvector.

    Note: For normalized vectors, inner product = cosine similarity.

    Args:
        session: SQLAlchemy session
        query_embedding: Query vector (384 dimensions)
        limit: Maximum number of results

    Returns:
        List of (document, score) tuples (higher is more similar)
    """
    from sqlalchemy import select

    # pgvector max_inner_product returns negative inner product for ordering
    # So we negate it to get the actual value
    query = (
        select(
            VectorDocument,
            (-VectorDocument.embedding.max_inner_product(query_embedding)).label('score')
        )
        .where(VectorDocument.embedding.isnot(None))
        .order_by(VectorDocument.embedding.max_inner_product(query_embedding))
        .limit(limit)
    )

    results = session.execute(query).all()
    return [(row[0], row[1]) for row in results]
