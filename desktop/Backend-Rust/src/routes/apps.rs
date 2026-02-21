// Apps routes - OMI Apps/Plugins system
// Endpoints for app discovery, management, and usage

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};

use std::collections::HashMap;

use crate::auth::AuthUser;
use crate::models::{
    App, AppCapabilityDef, AppCategory, AppGroup, AppReview, AppSummary, AppsV2Meta, AppsV2Query,
    AppsV2Response, CapabilityInfo, ListAppsQuery, PaginationMeta, SearchAppsQuery,
    SubmitReviewRequest, ToggleAppRequest, ToggleAppResponse, get_app_capabilities,
    get_app_categories, get_v2_capabilities,
};
use crate::AppState;
use crate::services::redis::RedisService;
use std::sync::Arc;

// ============================================================================
// Helper function to enrich apps with Redis data
// ============================================================================

/// Enrich apps with installs and ratings from Redis (matching Python backend behavior)
/// Python calculates rating_avg and rating_count at query time from reviews stored in Redis
async fn enrich_apps_from_redis(apps: &mut [AppSummary], redis: Option<&Arc<RedisService>>) {
    let Some(redis) = redis else { return };
    let app_ids: Vec<String> = apps.iter().map(|a| a.id.clone()).collect();
    if app_ids.is_empty() {
        return;
    }

    // Fetch installs
    if let Ok(installs_map) = redis.get_apps_installs_count(&app_ids).await {
        for app in apps.iter_mut() {
            if let Some(&installs) = installs_map.get(&app.id) {
                app.installs = installs;
            }
        }
    }

    // Fetch reviews and calculate ratings
    if let Ok(reviews_map) = redis.get_apps_reviews(&app_ids).await {
        for app in apps.iter_mut() {
            if let Some(reviews) = reviews_map.get(&app.id) {
                if !reviews.is_empty() {
                    let total_score: i32 = reviews.iter().map(|r| r.score).sum();
                    let count = reviews.len();
                    app.rating_avg = Some(total_score as f64 / count as f64);
                    app.rating_count = count as i32;
                }
            }
        }
    }
}

// ============================================================================
// App Discovery Endpoints
// ============================================================================

/// GET /v1/apps - List all available apps
async fn list_apps(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<ListAppsQuery>,
) -> Result<Json<Vec<AppSummary>>, (StatusCode, String)> {
    tracing::info!(
        "Listing apps for user {} with capability={:?}, category={:?}, limit={}, offset={}",
        user.uid,
        query.capability,
        query.category,
        query.limit,
        query.offset
    );

    let mut apps = match state
        .firestore
        .get_apps(&user.uid, query.limit, query.offset, query.capability.as_deref(), query.category.as_deref())
        .await
    {
        Ok(apps) => apps,
        Err(e) => {
            tracing::error!("Failed to get apps: {}", e);
            return Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to get apps: {}", e)));
        }
    };

    enrich_apps_from_redis(&mut apps, state.redis.as_ref()).await;
    Ok(Json(apps))
}

/// GET /v1/approved-apps - List public approved apps only
async fn list_approved_apps(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<ListAppsQuery>,
) -> Result<Json<Vec<AppSummary>>, (StatusCode, String)> {
    tracing::info!("Listing approved apps for user {}", user.uid);

    let mut apps = match state
        .firestore
        .get_approved_apps(&user.uid, query.limit, query.offset)
        .await
    {
        Ok(apps) => apps,
        Err(e) => {
            tracing::error!("Failed to get approved apps: {}", e);
            return Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to get approved apps: {}", e)));
        }
    };

    enrich_apps_from_redis(&mut apps, state.redis.as_ref()).await;
    Ok(Json(apps))
}

/// GET /v1/apps/popular - List popular apps
async fn list_popular_apps(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<Vec<AppSummary>>, (StatusCode, String)> {
    tracing::info!("Listing popular apps for user {}", user.uid);

    let mut apps = match state.firestore.get_popular_apps(&user.uid, 20).await {
        Ok(apps) => apps,
        Err(e) => {
            tracing::error!("Failed to get popular apps: {}", e);
            return Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to get popular apps: {}", e)));
        }
    };

    enrich_apps_from_redis(&mut apps, state.redis.as_ref()).await;
    Ok(Json(apps))
}

/// GET /v2/apps/search - Search apps with filters
async fn search_apps(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<SearchAppsQuery>,
) -> Result<Json<Vec<AppSummary>>, (StatusCode, String)> {
    tracing::info!(
        "Searching apps for user {} with query={:?}, category={:?}, capability={:?}",
        user.uid,
        query.query,
        query.category,
        query.capability
    );

    let mut apps = match state
        .firestore
        .search_apps(
            &user.uid,
            query.query.as_deref(),
            query.category.as_deref(),
            query.capability.as_deref(),
            query.rating,
            query.my_apps,
            query.installed_apps,
            query.limit,
            query.offset,
        )
        .await
    {
        Ok(apps) => apps,
        Err(e) => {
            tracing::error!("Failed to search apps: {}", e);
            return Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to search apps: {}", e)));
        }
    };

    enrich_apps_from_redis(&mut apps, state.redis.as_ref()).await;
    Ok(Json(apps))
}

/// GET /v2/apps - Get apps grouped by capability (matching Python backend)
/// Groups: Featured, Integrations, Chat Assistants, Summary Apps, Realtime Notifications
async fn get_apps_v2(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<AppsV2Query>,
) -> Result<Json<AppsV2Response>, (StatusCode, String)> {
    tracing::info!(
        "Getting v2 apps for user {} with capability={:?}, offset={}, limit={}",
        user.uid,
        query.capability,
        query.offset,
        query.limit
    );

    // Get all approved apps (high limit to match Python backend which fetches all from cache)
    let mut all_apps = match state
        .firestore
        .get_apps(&user.uid, 5000, 0, None, None)
        .await
    {
        Ok(apps) => apps,
        Err(e) => {
            tracing::error!("Failed to get apps for v2: {}", e);
            return Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to get apps: {}", e)));
        }
    };

    // Get popular apps separately (they have is_popular=true)
    let mut popular_apps = match state.firestore.get_popular_apps(&user.uid, 20).await {
        Ok(apps) => apps,
        Err(e) => {
            tracing::warn!("Failed to get popular apps: {}", e);
            vec![]
        }
    };

    // Fetch installs counts from Redis (matching Python backend behavior)
    // The Python backend stores installs in Redis, not Firestore
    if let Some(redis) = &state.redis {
        // Collect all app IDs
        let mut all_app_ids: Vec<String> = all_apps.iter().map(|a| a.id.clone()).collect();
        for app in &popular_apps {
            if !all_app_ids.contains(&app.id) {
                all_app_ids.push(app.id.clone());
            }
        }

        // Fetch installs from Redis
        match redis.get_apps_installs_count(&all_app_ids).await {
            Ok(installs_map) => {
                // Update all_apps with installs
                for app in &mut all_apps {
                    if let Some(&installs) = installs_map.get(&app.id) {
                        app.installs = installs;
                    }
                }
                // Update popular_apps with installs
                for app in &mut popular_apps {
                    if let Some(&installs) = installs_map.get(&app.id) {
                        app.installs = installs;
                    }
                }
                tracing::debug!("Updated {} apps with installs from Redis", installs_map.len());
            }
            Err(e) => {
                tracing::warn!("Failed to fetch installs from Redis: {} - using Firestore values", e);
            }
        }

        // Fetch reviews from Redis and calculate rating_avg/rating_count
        // Python backend stores reviews in Redis and calculates ratings at query time
        match redis.get_apps_reviews(&all_app_ids).await {
            Ok(reviews_map) => {
                // Update all_apps with calculated ratings
                for app in &mut all_apps {
                    if let Some(reviews) = reviews_map.get(&app.id) {
                        if !reviews.is_empty() {
                            let total_score: i32 = reviews.iter().map(|r| r.score).sum();
                            let count = reviews.len();
                            app.rating_avg = Some(total_score as f64 / count as f64);
                            app.rating_count = count as i32;
                        }
                    }
                }
                // Update popular_apps with calculated ratings
                for app in &mut popular_apps {
                    if let Some(reviews) = reviews_map.get(&app.id) {
                        if !reviews.is_empty() {
                            let total_score: i32 = reviews.iter().map(|r| r.score).sum();
                            let count = reviews.len();
                            app.rating_avg = Some(total_score as f64 / count as f64);
                            app.rating_count = count as i32;
                        }
                    }
                }
                tracing::debug!("Updated {} apps with ratings from Redis reviews", reviews_map.len());
            }
            Err(e) => {
                tracing::warn!("Failed to fetch reviews from Redis: {} - ratings may be missing", e);
            }
        }
    } else {
        tracing::debug!("Redis not configured - using installs from Firestore");
    }

    let popular_ids: std::collections::HashSet<_> = popular_apps.iter().map(|a| a.id.clone()).collect();

    // Get capabilities for grouping
    let capabilities = get_v2_capabilities();

    // Multi-pass grouping (matching Python backend behavior)
    let mut grouped: HashMap<String, Vec<AppSummary>> = HashMap::new();

    // Pass 1: Add popular apps
    if !popular_apps.is_empty() {
        grouped.insert("popular".to_string(), popular_apps);
    }

    // Pass 2: Collect notification apps (exclusive - they only appear in notifications section)
    // This includes apps with proactive_notification OR simple integrations without auth_steps
    let mut notification_ids: std::collections::HashSet<String> = std::collections::HashSet::new();
    for app in &all_apps {
        if is_notification_app(app) {
            notification_ids.insert(app.id.clone());
            grouped
                .entry("proactive_notification".to_string())
                .or_insert_with(Vec::new)
                .push(app.clone());
        }
    }

    // Pass 3: Group remaining apps by capability
    for app in &all_apps {
        // Skip popular apps (they're in their own section)
        if popular_ids.contains(&app.id) {
            continue;
        }

        // Skip notification apps (already processed in pass 2)
        if notification_ids.contains(&app.id) {
            continue;
        }

        // Skip persona apps (matching Python backend behavior)
        if app.capabilities.contains(&"persona".to_string()) {
            continue;
        }

        // Determine primary capability for this app
        if let Some(cap) = get_app_capability(app) {
            // Skip proactive_notification here (handled in pass 2)
            if cap != "proactive_notification" {
                grouped.entry(cap).or_insert_with(Vec::new).push(app.clone());
            }
        }
    }

    // Sort each group (matching Python backend behavior)
    // - Popular group: sort by installs only
    // - Other groups: sort by computed score, with installs as tiebreaker
    for (cap_id, apps) in grouped.iter_mut() {
        if cap_id == "popular" {
            // Popular apps sorted by installs only
            apps.sort_by(|a, b| b.installs.cmp(&a.installs));
        } else {
            // Other groups sorted by computed score, installs as tiebreaker
            apps.sort_by(|a, b| {
                let score_a = compute_app_score(a);
                let score_b = compute_app_score(b);
                match score_b.partial_cmp(&score_a) {
                    Some(std::cmp::Ordering::Equal) | None => {
                        // Tiebreaker: sort by installs descending
                        b.installs.cmp(&a.installs)
                    }
                    Some(ord) => ord,
                }
            });
        }
    }

    // Build response groups in the correct order
    let mut groups: Vec<AppGroup> = Vec::new();
    for cap_info in &capabilities {
        if let Some(apps) = grouped.get(&cap_info.id) {
            if apps.is_empty() {
                continue;
            }

            let total = apps.len();
            let start = query.offset.min(total);
            let end = (query.offset + query.limit).min(total);
            let page: Vec<AppSummary> = apps[start..end].to_vec();

            groups.push(AppGroup {
                capability: CapabilityInfo {
                    id: cap_info.id.clone(),
                    title: cap_info.title.clone(),
                },
                data: page,
                pagination: PaginationMeta {
                    total,
                    count: end - start,
                    offset: query.offset,
                    limit: query.limit,
                },
            });
        }
    }

    let response = AppsV2Response {
        groups,
        meta: AppsV2Meta {
            capabilities: capabilities.clone(),
            group_count: grouped.len(),
            limit: query.limit,
            offset: query.offset,
        },
    };

    Ok(Json(response))
}

/// Compute app ranking score (matching Python backend formula)
/// Formula: ((rating_avg / 5) ** 2) * log(1 + rating_count) * sqrt(log(1 + installs))
/// - Power of 2 on rating makes ratings below 3.0 fall steeply
/// - sqrt on installs reduces dependence on install count
fn compute_app_score(app: &AppSummary) -> f64 {
    let rating_avg = app.rating_avg.unwrap_or(0.0);
    let rating_count = app.rating_count as f64;
    let installs = app.installs as f64;

    let rating_factor = (rating_avg / 5.0).powi(2); // Steep drop for low ratings
    let score = rating_factor * (1.0 + rating_count).ln() * (1.0 + installs).ln().sqrt();

    // Round to 4 decimal places
    (score * 10000.0).round() / 10000.0
}

/// Check if app is a notification/simple integration app (matching Python backend logic)
/// Returns true for:
/// - Apps with proactive_notification capability
/// - Simple integrations (external_integration WITHOUT auth_steps, chat, or memories)
fn is_notification_app(app: &AppSummary) -> bool {
    // Case 1: Has proactive_notification capability
    if app.capabilities.contains(&"proactive_notification".to_string()) {
        return true;
    }

    // Case 2: Simple integration (external_integration WITHOUT auth_steps, chat, or memories)
    let has_external = app.capabilities.contains(&"external_integration".to_string());
    has_external
        && !app.has_auth_steps
        && !app.capabilities.contains(&"chat".to_string())
        && !app.capabilities.contains(&"memories".to_string())
}

/// Determine the primary capability section for an app (matching Python backend logic)
/// Priority: notification apps -> external_integration (with auth) -> chat -> memories
fn get_app_capability(app: &AppSummary) -> Option<String> {
    let has_external = app.capabilities.contains(&"external_integration".to_string());

    // First: notification apps (including simple integrations without auth_steps)
    if is_notification_app(app) {
        return Some("proactive_notification".to_string());
    }

    // Second: external integration WITH auth_steps only
    if has_external && app.has_auth_steps {
        return Some("external_integration".to_string());
    }

    // Third: chat apps (if no external+auth)
    if app.capabilities.contains(&"chat".to_string()) {
        if !has_external || !app.has_auth_steps {
            return Some("chat".to_string());
        }
    }

    // Fourth: memories apps (if no chat, no external+auth)
    if app.capabilities.contains(&"memories".to_string())
        && !app.capabilities.contains(&"chat".to_string())
    {
        if !has_external || !app.has_auth_steps {
            return Some("memories".to_string());
        }
    }

    None
}

// ============================================================================
// App Details Endpoints
// ============================================================================

/// GET /v1/apps/:app_id - Get app details
async fn get_app_details(
    State(state): State<AppState>,
    user: AuthUser,
    Path(app_id): Path<String>,
) -> Result<Json<App>, (StatusCode, String)> {
    tracing::info!("Getting app details for {} by user {}", app_id, user.uid);

    let mut app = match state.firestore.get_app(&user.uid, &app_id).await {
        Ok(Some(app)) => app,
        Ok(None) => return Err((StatusCode::NOT_FOUND, "App not found".to_string())),
        Err(e) => {
            tracing::error!("Failed to get app: {}", e);
            return Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to get app: {}", e)));
        }
    };

    // Fetch installs and ratings from Redis (matching Python backend behavior)
    if let Some(redis) = &state.redis {
        let app_ids = vec![app_id.clone()];

        // Fetch installs
        if let Ok(installs_map) = redis.get_apps_installs_count(&app_ids).await {
            if let Some(&installs) = installs_map.get(&app_id) {
                app.installs = installs;
            }
        }

        // Fetch reviews and calculate ratings
        if let Ok(reviews_map) = redis.get_apps_reviews(&app_ids).await {
            if let Some(reviews) = reviews_map.get(&app_id) {
                if !reviews.is_empty() {
                    let total_score: i32 = reviews.iter().map(|r| r.score).sum();
                    let count = reviews.len();
                    app.rating_avg = Some(total_score as f64 / count as f64);
                    app.rating_count = count as i32;
                }
            }
        }
    }

    Ok(Json(app))
}

/// GET /v1/apps/:app_id/reviews - Get app reviews
async fn get_app_reviews(
    State(state): State<AppState>,
    _user: AuthUser,
    Path(app_id): Path<String>,
) -> Result<Json<Vec<AppReview>>, (StatusCode, String)> {
    tracing::info!("Getting reviews for app {}", app_id);

    match state.firestore.get_app_reviews(&app_id).await {
        Ok(reviews) => Ok(Json(reviews)),
        Err(e) => {
            tracing::error!("Failed to get reviews: {}", e);
            Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to get reviews: {}", e)))
        }
    }
}

// ============================================================================
// App Management Endpoints
// ============================================================================

/// POST /v1/apps/enable - Enable an app for the user
async fn enable_app(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<ToggleAppRequest>,
) -> Result<Json<ToggleAppResponse>, (StatusCode, String)> {
    tracing::info!("Enabling app {} for user {}", request.app_id, user.uid);

    match state.firestore.enable_app(&user.uid, &request.app_id).await {
        Ok(_) => Ok(Json(ToggleAppResponse {
            success: true,
            message: "App enabled successfully".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to enable app: {}", e);
            Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to enable app: {}", e)))
        }
    }
}

/// POST /v1/apps/disable - Disable an app for the user
async fn disable_app(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<ToggleAppRequest>,
) -> Result<Json<ToggleAppResponse>, (StatusCode, String)> {
    tracing::info!("Disabling app {} for user {}", request.app_id, user.uid);

    match state.firestore.disable_app(&user.uid, &request.app_id).await {
        Ok(_) => Ok(Json(ToggleAppResponse {
            success: true,
            message: "App disabled successfully".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to disable app: {}", e);
            Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to disable app: {}", e)))
        }
    }
}

/// GET /v1/apps/enabled - Get user's enabled apps
async fn get_enabled_apps(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<Vec<AppSummary>>, (StatusCode, String)> {
    tracing::info!("Getting enabled apps for user {}", user.uid);

    let mut apps = match state.firestore.get_enabled_apps(&user.uid).await {
        Ok(apps) => apps,
        Err(e) => {
            tracing::error!("Failed to get enabled apps: {}", e);
            return Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to get enabled apps: {}", e)));
        }
    };

    enrich_apps_from_redis(&mut apps, state.redis.as_ref()).await;
    Ok(Json(apps))
}

// ============================================================================
// Review Endpoints
// ============================================================================

/// POST /v1/apps/review - Submit a review for an app
async fn submit_review(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<SubmitReviewRequest>,
) -> Result<Json<AppReview>, (StatusCode, String)> {
    tracing::info!(
        "User {} submitting review for app {} with score {}",
        user.uid,
        request.app_id,
        request.score
    );

    // Validate score
    if request.score < 1 || request.score > 5 {
        return Err((StatusCode::BAD_REQUEST, "Score must be between 1 and 5".to_string()));
    }

    match state
        .firestore
        .submit_app_review(&user.uid, &request.app_id, request.score, &request.review)
        .await
    {
        Ok(review) => Ok(Json(review)),
        Err(e) => {
            tracing::error!("Failed to submit review: {}", e);
            Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to submit review: {}", e)))
        }
    }
}

// ============================================================================
// Metadata Endpoints
// ============================================================================

/// GET /v1/app-categories - Get all app categories
async fn list_categories(
    _user: AuthUser,
) -> Result<Json<Vec<AppCategory>>, (StatusCode, String)> {
    Ok(Json(get_app_categories()))
}

/// GET /v1/app-capabilities - Get all app capabilities
async fn list_capabilities(
    _user: AuthUser,
) -> Result<Json<Vec<AppCapabilityDef>>, (StatusCode, String)> {
    Ok(Json(get_app_capabilities()))
}

// ============================================================================
// Router
// ============================================================================

pub fn apps_routes() -> Router<AppState> {
    Router::new()
        // Discovery
        .route("/v1/apps", get(list_apps))
        .route("/v1/approved-apps", get(list_approved_apps))
        .route("/v1/apps/popular", get(list_popular_apps))
        .route("/v2/apps", get(get_apps_v2))
        .route("/v2/apps/search", get(search_apps))
        // Details
        .route("/v1/apps/:app_id", get(get_app_details))
        .route("/v1/apps/:app_id/reviews", get(get_app_reviews))
        // Management
        .route("/v1/apps/enable", post(enable_app))
        .route("/v1/apps/disable", post(disable_app))
        .route("/v1/apps/enabled", get(get_enabled_apps))
        // Reviews
        .route("/v1/apps/review", post(submit_review))
        // Metadata
        .route("/v1/app-categories", get(list_categories))
        .route("/v1/app-capabilities", get(list_capabilities))
}
