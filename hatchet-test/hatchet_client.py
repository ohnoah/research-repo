"""Shared Hatchet client instance."""
import os

# Set defaults for local development
os.environ.setdefault("HATCHET_CLIENT_GRPC_HOST", "localhost")
os.environ.setdefault("HATCHET_CLIENT_GRPC_PORT", "7077")

from hatchet_sdk import Hatchet

hatchet = Hatchet(debug=True)
