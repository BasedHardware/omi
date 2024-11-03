import pytest
from database._client import get_firestore, get_async_firestore, transaction
from unittest.mock import patch, MagicMock, call
from google.cloud import firestore
from google.cloud.firestore_v1.transaction import Transaction

@pytest.fixture
def mock_firestore_client():
    """Mock firestore client"""
    with patch('database._client._db', None):  # Reset singleton
        with patch('database._client.firestore.Client') as mock:
            mock_instance = mock.return_value
            # Setup basic collection/document structure
            mock_doc = MagicMock()
            mock_collection = MagicMock()
            mock_instance.collection.return_value = mock_collection
            mock_collection.document.return_value = mock_doc
            yield mock_instance

@pytest.fixture
def mock_async_client():
    """Mock async firestore client"""
    with patch('database._client.AsyncClient') as mock:
        mock_instance = mock.return_value
        # Setup basic async collection/document structure
        mock_doc = MagicMock()
        mock_collection = MagicMock()
        mock_instance.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_doc
        yield mock_instance

class TestFirestoreConnection:
    def test_get_firestore_client(self, mock_firestore_client):
        client = get_firestore() 
        assert client is mock_firestore_client
        # Test singleton pattern
        client2 = get_firestore()
        assert client is client2

    def test_get_firestore_client_with_error(self):
        with patch('database._client.firestore.Client', side_effect=Exception("Connection error")):
            with pytest.raises(Exception) as exc:
                get_firestore()
            assert "Connection error" in str(exc.value)

    def test_get_async_firestore_client(self, mock_async_client):
        client = get_async_firestore()
        assert client is mock_async_client
        # Test singleton pattern
        client2 = get_async_firestore()
        assert client is client2

    def test_get_async_firestore_client_with_error(self):
        with patch('database._client.AsyncClient', side_effect=Exception("Connection error")):
            with pytest.raises(Exception) as exc:
                get_async_firestore()
            assert "Connection error" in str(exc.value)

class TestTransactions:
    def test_successful_transaction(self, mock_firestore_client):
        def mock_run_transaction(transaction_func, *args, **kwargs):
            mock_transaction = MagicMock(spec=Transaction)
            return transaction_func(mock_transaction)
            
        mock_firestore_client.run_transaction = mock_run_transaction
        
        @transaction
        def transaction_func(transaction):
            return "success"
        
        result = transaction_func()
        assert result == "success"

    def test_failed_transaction_retry(self, mock_firestore_client):
        attempt_count = 0
        def mock_run_transaction(transaction_func, *args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            raise Exception(f"Transaction failed attempt {attempt_count}")
            
        mock_firestore_client.run_transaction = mock_run_transaction
        
        @transaction
        def transaction_func(transaction):
            return "success"
        
        with pytest.raises(Exception) as exc:
            transaction_func()
        assert "Transaction failed attempt 1" in str(exc.value)

    def test_transaction_with_args(self, mock_firestore_client):
        def mock_run_transaction(transaction_func, *args, **kwargs):
            mock_transaction = MagicMock(spec=Transaction)
            return transaction_func(mock_transaction)
            
        mock_firestore_client.run_transaction = mock_run_transaction
        
        @transaction
        def transaction_func(transaction, arg1, kwarg1=None):
            return f"{arg1}-{kwarg1}"
        
        result = transaction_func("test", kwarg1="value")
        assert result == "test-value"

    def test_transaction_with_complex_operations(self, mock_firestore_client):
        def mock_run_transaction(transaction_func, *args, **kwargs):
            mock_transaction = MagicMock(spec=Transaction)
            return transaction_func(mock_transaction)
            
        mock_firestore_client.run_transaction = mock_run_transaction
        
        @transaction
        def complex_transaction(transaction):
            # Simulate multiple operations in transaction
            transaction.set('collection/doc1', {'field': 'value1'})
            transaction.update('collection/doc2', {'field': 'value2'})
            transaction.delete('collection/doc3')
            return "completed"
        
        result = complex_transaction()
        assert result == "completed"

    def test_nested_transactions(self, mock_firestore_client):
        transaction_results = []
        
        def mock_run_transaction(transaction_func, *args, **kwargs):
            mock_transaction = MagicMock(spec=Transaction)
            result = transaction_func(mock_transaction)
            transaction_results.append(result)
            return result
            
        mock_firestore_client.run_transaction = mock_run_transaction
        
        @transaction
        def inner_transaction(transaction):
            return "inner"
            
        @transaction
        def outer_transaction(transaction):
            inner_result = inner_transaction()
            return f"outer-{inner_result}"
        
        result = outer_transaction()
        assert result == "outer-inner"
        assert len(transaction_results) == 2  # Verify both transactions were executed
        assert transaction_results == ["inner", "outer-inner"]

    def test_transaction_exception_handling(self, mock_firestore_client):
        class CustomTransactionError(Exception):
            pass

        def mock_run_transaction(transaction_func, *args, **kwargs):
            mock_transaction = MagicMock(spec=Transaction)
            mock_transaction.get.side_effect = CustomTransactionError("Custom error")
            return transaction_func(mock_transaction)
            
        mock_firestore_client.run_transaction = mock_run_transaction
        
        @transaction
        def failing_transaction(transaction):
            transaction.get('collection/doc')
            return "success"
        
        with pytest.raises(CustomTransactionError) as exc:
            failing_transaction()
        assert "Custom error" in str(exc.value)

    def test_transaction_with_batch_operations(self, mock_firestore_client):
        operations = []
        
        def mock_run_transaction(transaction_func, *args, **kwargs):
            mock_transaction = MagicMock(spec=Transaction)
            def record_operation(path, data):
                operations.append((path, data))
            mock_transaction.set.side_effect = record_operation
            return transaction_func(mock_transaction)
            
        mock_firestore_client.run_transaction = mock_run_transaction
        
        @transaction
        def batch_transaction(transaction):
            # Simulate batch operations
            docs = [f"doc{i}" for i in range(3)]
            for doc in docs:
                transaction.set(f'collection/{doc}', {'field': f'value_{doc}'})
            return len(docs)
        
        result = batch_transaction()
        assert result == 3
        assert len(operations) == 3
        assert all(op[0].startswith('collection/doc') for op in operations)

    def test_transaction_with_read_operations(self, mock_firestore_client):
        def mock_run_transaction(transaction_func, *args, **kwargs):
            mock_transaction = MagicMock(spec=Transaction)
            mock_doc = MagicMock()
            mock_doc.to_dict.return_value = {'field': 'value'}
            mock_transaction.get.return_value = mock_doc
            return transaction_func(mock_transaction)
            
        mock_firestore_client.run_transaction = mock_run_transaction
        
        @transaction
        def read_transaction(transaction):
            doc = transaction.get('collection/doc')
            return doc.to_dict()['field']
        
        result = read_transaction()
        assert result == 'value'