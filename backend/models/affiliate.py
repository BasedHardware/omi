from typing import List, Literal, Optional

from pydantic import BaseModel, Field

AffiliateState = Literal['unavailable', 'not_linked', 'linked', 'blocked']
LinkMethod = Literal['email_match', 'affiliate_login', 'joined']


class AffiliateProfile(BaseModel):
    affiliate_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    ref_code: Optional[str] = None
    coupon: Optional[str] = None
    referral_url: Optional[str] = None


class AffiliateStatusResponse(BaseModel):
    native_enabled: bool = Field(description='False: clients keep opening the affiliate website')
    state: AffiliateState
    email_match_available: bool = False
    profile: Optional[AffiliateProfile] = None


class AffiliateLinkCredentialsRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class AffiliateLinkResponse(BaseModel):
    method: LinkMethod
    status: AffiliateStatusResponse


class AffiliateStatsResponse(BaseModel):
    total_sales: float
    total_commission: float
    total_clicks: int
    total_orders: int
    paid_commission: float
    unpaid_commission: float


class AffiliateOrder(BaseModel):
    id: str
    number: Optional[str] = None
    created_at: Optional[str] = None
    total: Optional[float] = None
    commission: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None


class AffiliateOrdersResponse(BaseModel):
    orders: List[AffiliateOrder]
    count: Optional[int] = None


class AffiliateTransaction(BaseModel):
    id: str
    created_at: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    entity_type: Optional[str] = None
    event_type: Optional[str] = None
    order_number: Optional[str] = None
    status: Optional[str] = None


class AffiliateCommission(BaseModel):
    name: Optional[str] = None
    commission_type: Optional[str] = Field(default=None, description="'percentage' or a fixed amount")
    commission_value: Optional[float] = None
    commission_on: Optional[str] = None
    standard: bool = False


class AffiliateEarningsResponse(BaseModel):
    commissions: List[AffiliateCommission]
    transactions: List[AffiliateTransaction]


AffiliatePayoutStatus = Literal['completed', 'transferred', 'reversed']


class AffiliatePayout(BaseModel):
    id: str
    date: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    payment_method: Optional[str] = None
    status: AffiliatePayoutStatus = 'completed'


class AffiliatePayoutsResponse(BaseModel):
    payouts: List[AffiliatePayout]
    count: Optional[int] = None


class AffiliateRefCodeAvailabilityResponse(BaseModel):
    available: bool
    current: bool = False
    error: Optional[str] = None


class AffiliateRefCodeUpdateRequest(BaseModel):
    ref_code: str = Field(min_length=1, max_length=64)


class AffiliateRefCodeUpdateResponse(BaseModel):
    ref_code: str
    referral_url: str
    unchanged: bool = False


class AffiliatePayoutSetupRequest(BaseModel):
    country: Optional[str] = Field(default=None, min_length=2, max_length=2)


class AffiliatePayoutLinkResponse(BaseModel):
    url: str


class AffiliatePayoutAccountStatusResponse(BaseModel):
    connected: bool
    has_account: bool
    payouts_enabled: bool = False
    details_submitted: bool = False
    has_issues: bool = False
    currently_due: List[str] = []
