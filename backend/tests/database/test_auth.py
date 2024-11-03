import pytest
from database.auth import create_user, get_user, delete_user, validate_token, update_user
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

@pytest.fixture
def mock_firestore():
    """Mock firestore with proper document references"""
    with patch('database._client._db', None):  # Reset singleton
        with patch('database._client.firestore.Client') as mock_client:
            # Create mock document
            mock_doc = MagicMock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {"name": "Test User"}
            
            # Create mock document reference
            mock_doc_ref = MagicMock()
            mock_doc_ref.get.return_value = mock_doc
            
            # Setup collection mock
            mock_collection = MagicMock()
            mock_collection.document.return_value = mock_doc_ref
            
            # Setup firestore mock
            mock_client_instance = mock_client.return_value
            mock_client_instance.collection.return_value = mock_collection
            
            yield mock_client_instance

@pytest.fixture
def mock_firebase_auth():
    """Mock firebase auth"""
    with patch('database.auth.auth') as mock:
        mock.verify_id_token.return_value = {"uid": "user123"}
        yield mock

class TestUserCRUD:
    def test_create_user(self, mock_firestore):
        user_data = {
            "email": "test@example.com",
            "name": "Test User"
        }
        mock_doc_ref = mock_firestore.collection().document()
        result = create_user("user123", user_data)
        
        mock_doc_ref.set.assert_called_once_with(user_data)
        assert result == "user123"

    def test_get_user(self, mock_firestore):
        mock_doc = mock_firestore.collection().document().get()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"name": "Test User"}
        
        user = get_user("user123")
        assert user == {"name": "Test User"}

    def test_get_nonexistent_user(self, mock_firestore):
        mock_doc = mock_firestore.collection().document().get()
        mock_doc.exists = False
        
        with pytest.raises(HTTPException) as exc:
            get_user("nonexistent")
        assert exc.value.status_code == 404

    def test_delete_user(self, mock_firestore):
        mock_doc_ref = mock_firestore.collection().document()
        delete_user("user123")
        mock_doc_ref.delete.assert_called_once()

class TestTokenValidation:
    def test_validate_valid_token(self, mock_firebase_auth):
        result = validate_token("valid_token")
        assert result == "user123"
        mock_firebase_auth.verify_id_token.assert_called_once_with("valid_token")

    def test_validate_invalid_token(self, mock_firebase_auth):
        mock_firebase_auth.verify_id_token.side_effect = Exception("Invalid token")
        
        with pytest.raises(HTTPException) as exc:
            validate_token("invalid_token")
        assert exc.value.status_code == 401

    def test_validate_expired_token(self, mock_firebase_auth):
        mock_firebase_auth.verify_id_token.side_effect = Exception("Token expired")
        
        with pytest.raises(HTTPException) as exc:
            validate_token("expired_token")
        assert exc.value.status_code == 401