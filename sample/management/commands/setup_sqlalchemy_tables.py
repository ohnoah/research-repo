"""
Management command to set up SQLAlchemy tables.

Creates the pgvector tables using SQLAlchemy (not Django migrations).
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create SQLAlchemy/pgvector tables using direct connection'

    def add_arguments(self, parser):
        parser.add_argument(
            '--drop',
            action='store_true',
            help='Drop existing tables before creating'
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=0,
            help='Seed with N sample documents'
        )

    def handle(self, *args, **options):
        import random
        from sample.sqlalchemy_models import (
            create_tables,
            drop_tables,
            VectorDocument,
            direct_session_scope,
        )

        if options['drop']:
            self.stdout.write('Dropping existing SQLAlchemy tables...')
            drop_tables()
            self.stdout.write(self.style.SUCCESS('Tables dropped.'))

        self.stdout.write('Creating SQLAlchemy tables...')
        create_tables()
        self.stdout.write(self.style.SUCCESS('Tables created successfully.'))

        if options['seed'] > 0:
            count = options['seed']
            self.stdout.write(f'Seeding {count} sample documents...')

            categories = ['tech', 'science', 'art', 'history', 'music']
            topics = [
                'machine learning', 'quantum physics', 'renaissance painting',
                'ancient rome', 'jazz music', 'web development', 'astronomy',
                'modern art', 'medieval history', 'classical music'
            ]

            with direct_session_scope() as session:
                for i in range(count):
                    doc = VectorDocument(
                        title=f"Document {i}: {random.choice(topics).title()}",
                        content=(
                            f"This is sample document {i} about {random.choice(topics)}. "
                            f"It contains information that would be useful for semantic search "
                            f"and similarity matching operations using pgvector."
                        ),
                        doc_metadata={
                            'category': random.choice(categories),
                            'index': i,
                        },
                        embedding=[random.gauss(0, 1) for _ in range(384)]
                    )
                    session.add(doc)

            self.stdout.write(
                self.style.SUCCESS(f'Seeded {count} documents with embeddings.')
            )
