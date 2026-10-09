from sqlalchemy import Column, String, DateTime
from backend.models.base import Base
import uuid

class WebhookDestination(Base):
    __tablename__ = "webhook_destinations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    url = Column(String, nullable=False)
    webhook_type = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    
    # Novo campo para o segredo de assinatura
    # Armazenado como hash ou string segura (para este MVP, trataremos como string criptografada/protegida)
    signing_secret = Column(String, nullable=True)
    
    is_active = Column(Boolean, default=True)
    last_delivered_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0)
