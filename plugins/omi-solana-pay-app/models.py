"""Pydantic request and response schemas for Omi Solana Pay Plugin."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatToolResponse(BaseModel):
    """Standard Omi chat tool response format."""
    result: Optional[str] = Field(default=None, description="Human-readable result for Omi user or LLM context.")
    error: Optional[str] = Field(default=None, description="Error message if operation failed.")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Structured payload for programmatic consumers.")


class CheckSolanaBalanceRequest(BaseModel):
    """Request payload to query on-chain balance."""
    wallet_address: str = Field(
        ...,
        description="Solana base58 wallet address or pubkey to query (e.g. 'FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8')."
    )
    network: Optional[str] = Field(
        default="mainnet",
        description="Solana cluster to query: 'mainnet' or 'devnet'."
    )


class ParseSolanaPayRequest(BaseModel):
    """Request payload to parse a Solana Pay QR code string or URI."""
    solana_pay_url: str = Field(
        ...,
        description="Raw Solana Pay URI (e.g. 'solana:mvines9iiHiQTysrwkJjGNT2ecPdvtVuRtMmKdYtnr5?amount=0.01&label=Coffee%20Shop')."
    )


class SimulatePaymentVoiceIntentRequest(BaseModel):
    """Request payload to generate spoken voice confirmation dialogue for Omi wearable."""
    recipient: str = Field(..., description="Recipient wallet or merchant label.")
    amount: float = Field(..., ge=0.0, description="Amount to transfer.")
    currency: Optional[str] = Field(default="USDC", description="Token symbol: 'USDC', 'SOL', etc.")
    memo: Optional[str] = Field(default=None, description="Optional payment reference or receipt memo.")


class VerifyTransactionRequest(BaseModel):
    """Request payload to verify on-chain transaction finality."""
    signature: str = Field(..., description="Solana base58 transaction signature to verify.")
    network: Optional[str] = Field(default="mainnet", description="Solana cluster: 'mainnet' or 'devnet'.")
