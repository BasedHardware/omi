import pytest
from database._client import get_firestore, get_async_firestore, transaction
from unittest.mock import patch, MagicMock
from google.cloud import firestore

@pytest.fixture
def mock_firestore_client():
    """Mock firestore client"""
    with patch('database._client._db', None):  # Reset singleton
        with patch('database._client.firestore.Client') as mock:
            mock_instance = mock.return_value
            yield mock_instance

@pytest.fixture
def mock_async_client():
    """Mock async firestore client"""
    with patch('database._client.AsyncClient') as mock:
        mock_instance = mock.return_value
        yield mock_instance

class TestFirestoreConnection:
    def test_get_firestore_client(self, mock_firestore_client):
        client = get_firestore() 
        assert client is mock_firestore_client

    def test_get_async_firestore_client(self, mock_async_client):
        client = get_async_firestore()
        assert client is mock_async_client

class TestTransactions:
    def test_successful_transaction(self, mock_firestore_client):
        def mock_run_transaction(transaction_func, *args, **kwargs):
            mock_transaction = MagicMock()
            return transaction_func(mock_transaction)
            
        mock_firestore_client.run_transaction = mock_run_transaction
        
        @transaction
        def transaction_func(transaction):
            return "success"
        
        result = transaction_func()
        assert result == "success"

    def test_failed_transaction_retry(self, mock_firestore_client):
        mock_firestore_client.run_transaction.side_effect = Exception("Transaction failed")
        
        @transaction
        def transaction_func(transaction):
            return "success"
        
        with pytest.raises(Exception) as exc:
            transaction_func()
        assert str(exc.value) == "Transaction failed"

    def test_transaction_with_args(self, mock_firestore_client):
        def mock_run_transaction(transaction_func, *args, **kwargs):
            mock_transaction = MagicMock()
            return transaction_func(mock_transaction)
            
        mock_firestore_client.run_transaction = mock_run_transaction
        
        @transaction
        def transaction_func(transaction, arg1, kwarg1=None):
            return f"{arg1}-{kwarg1}"
        
        result = transaction_func("test", kwarg1="value")
        assert result == "test-value"