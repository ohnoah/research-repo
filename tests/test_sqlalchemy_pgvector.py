"""
Tests for SQLAlchemy with pgvector operations.

These tests verify:
- SQLAlchemy table creation
- Document CRUD operations
- Vector similarity search
- Prepared statement behavior
- Connection reuse patterns
"""

import pytest
import random


@pytest.fixture
def sqlalchemy_setup(db):
    """Set up SQLAlchemy tables for tests."""
    from sample.sqlalchemy_models import create_tables, drop_tables

    # Create tables
    create_tables()
    yield
    # Cleanup is optional since we're using test DB


@pytest.fixture
def sample_documents(sqlalchemy_setup):
    """Create sample documents with embeddings."""
    from sample.sqlalchemy_models import VectorDocument, direct_session_scope

    docs = []
    with direct_session_scope() as session:
        for i in range(20):
            doc = VectorDocument(
                title=f"Test Document {i}",
                content=f"Content for test document {i}",
                metadata={"index": i},
                embedding=[random.gauss(0, 1) for _ in range(384)]
            )
            session.add(doc)
            docs.append(doc)

    return docs


class TestDocumentCRUD:
    """Test SQLAlchemy document CRUD operations."""

    @pytest.mark.django_db
    def test_create_document(self, api_client, sqlalchemy_setup):
        """Test creating a document through the API."""
        response = api_client.post(
            "/vectors/documents",
            json={
                "title": "API Created Document",
                "content": "Created via API",
                "metadata": {"source": "test"}
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "API Created Document"
        assert data["has_embedding"] is False

    @pytest.mark.django_db
    def test_create_document_with_embedding(self, api_client, sqlalchemy_setup):
        """Test creating a document with embedding."""
        embedding = [random.gauss(0, 1) for _ in range(384)]
        response = api_client.post(
            "/vectors/documents",
            json={
                "title": "Document with Embedding",
                "content": "Has a vector embedding",
                "embedding": embedding
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_embedding"] is True

    @pytest.mark.django_db
    def test_list_documents(self, api_client, sample_documents):
        """Test listing documents."""
        response = api_client.get("/vectors/documents?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 10


class TestVectorSearch:
    """Test pgvector similarity search operations."""

    @pytest.mark.django_db
    def test_cosine_similarity_search(self, api_client, sample_documents):
        """Test cosine similarity search."""
        query_embedding = [random.gauss(0, 1) for _ in range(384)]
        response = api_client.post(
            "/vectors/search/cosine",
            json={
                "query_embedding": query_embedding,
                "limit": 5,
                "use_pooled": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 5
        # Results should have similarity scores
        if len(data) > 0:
            assert "similarity_score" in data[0]

    @pytest.mark.django_db
    def test_l2_distance_search(self, api_client, sample_documents):
        """Test L2 distance search."""
        query_embedding = [random.gauss(0, 1) for _ in range(384)]
        response = api_client.post(
            "/vectors/search/l2",
            json={
                "query_embedding": query_embedding,
                "limit": 5
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 5


class TestPreparedStatements:
    """Test prepared statement behavior."""

    @pytest.mark.django_db
    def test_prepared_statements_pooled(self, api_client, sample_documents):
        """Test prepared statements through PgBouncer."""
        response = api_client.get(
            "/vectors/test/prepared-statements?iterations=50&use_pooled=true"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["iterations"] == 50
        assert data["connection_type"] == "pooled"
        assert "avg_query_time_ms" in data

    @pytest.mark.django_db
    def test_prepared_statements_direct(self, api_client, sample_documents):
        """Test prepared statements on direct connection."""
        response = api_client.get(
            "/vectors/test/prepared-statements?iterations=50&use_pooled=false"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["iterations"] == 50
        assert data["connection_type"] == "direct"


class TestConnectionReuse:
    """Test connection reuse patterns."""

    @pytest.mark.django_db
    def test_connection_reuse_pooled(self, api_client, sqlalchemy_setup):
        """Test connection reuse through PgBouncer."""
        response = api_client.get(
            "/vectors/test/connection-reuse?queries=10&use_pooled=true"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["queries"] == 10
        assert len(data["backend_pids"]) == 10

    @pytest.mark.django_db
    def test_connection_reuse_direct(self, api_client, sqlalchemy_setup):
        """Test connection reuse on direct connection."""
        response = api_client.get(
            "/vectors/test/connection-reuse?queries=10&use_pooled=false"
        )
        assert response.status_code == 200
        data = response.json()
        # Within a session, should use the same connection
        assert data["unique_pids"] == 1


class TestSetup:
    """Test setup endpoints."""

    @pytest.mark.django_db
    def test_create_tables(self, api_client):
        """Test table creation endpoint."""
        response = api_client.post("/vectors/setup/create-tables")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.django_db
    def test_seed_data(self, api_client, sqlalchemy_setup):
        """Test data seeding endpoint."""
        response = api_client.post("/vectors/setup/seed-data?count=10")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["documents_created"] == 10
