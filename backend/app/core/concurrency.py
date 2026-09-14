# core/concurrency.py - Shared short-write lock for the single-worker SQLite deployment.
import asyncio

# Bedrock network calls must never hold this lock.
mutation_lock = asyncio.Lock()
