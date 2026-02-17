// Daily Score routes
// Endpoint: GET /v1/daily-score, GET /v1/scores

use axum::{
    extract::{Query, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};
use chrono::{NaiveDate, Utc, Duration};

use crate::auth::AuthUser;
use crate::models::{DailyScore, DailyScoreQuery, ScoreResponse, ScoreData};
use crate::AppState;

/// GET /v1/daily-score - Calculate daily score from action items due today (legacy endpoint)
async fn get_daily_score(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<DailyScoreQuery>,
) -> Result<Json<DailyScore>, StatusCode> {
    // Parse date or use today
    let date = match query.date {
        Some(date_str) => {
            NaiveDate::parse_from_str(&date_str, "%Y-%m-%d")
                .map_err(|_| {
                    tracing::error!("Invalid date format: {}", date_str);
                    StatusCode::BAD_REQUEST
                })?
        }
        None => Utc::now().date_naive(),
    };

    let date_str = date.format("%Y-%m-%d").to_string();
    tracing::info!("Getting daily score for user {} on {}", user.uid, date_str);

    // Calculate start and end of day in UTC
    let due_start = format!("{}T00:00:00Z", date_str);
    let due_end = format!("{}T23:59:59.999Z", date_str);

    match state
        .firestore
        .get_action_items_for_daily_score(&user.uid, &due_start, &due_end)
        .await
    {
        Ok((completed_tasks, total_tasks)) => {
            // Match Flutter behavior: 0 when no tasks, percentage when tasks exist
            let score = if total_tasks > 0 {
                (completed_tasks as f64 / total_tasks as f64) * 100.0
            } else {
                0.0 // No tasks = 0 score (matches Flutter)
            };

            Ok(Json(DailyScore {
                score,
                completed_tasks,
                total_tasks,
                date: date_str,
            }))
        }
        Err(e) => {
            tracing::error!("Failed to calculate daily score: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// GET /v1/scores - Get all three scores (daily, weekly, overall) with default tab selection
async fn get_scores(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<DailyScoreQuery>,
) -> Result<Json<ScoreResponse>, StatusCode> {
    // Parse date or use today
    let date = match query.date {
        Some(date_str) => {
            NaiveDate::parse_from_str(&date_str, "%Y-%m-%d")
                .map_err(|_| {
                    tracing::error!("Invalid date format: {}", date_str);
                    StatusCode::BAD_REQUEST
                })?
        }
        None => Utc::now().date_naive(),
    };

    let date_str = date.format("%Y-%m-%d").to_string();
    tracing::info!("Getting all scores for user {} on {}", user.uid, date_str);

    // Calculate date ranges
    let today_start = format!("{}T00:00:00Z", date_str);
    let today_end = format!("{}T23:59:59.999Z", date_str);

    // 7 days ago
    let week_ago = date - Duration::days(7);
    let week_start = format!("{}T00:00:00Z", week_ago.format("%Y-%m-%d"));

    // Get all three scores in parallel
    let (daily_result, weekly_result, overall_result) = tokio::join!(
        state.firestore.get_action_items_for_daily_score(&user.uid, &today_start, &today_end),
        state.firestore.get_action_items_for_weekly_score(&user.uid, &week_start, &today_end),
        state.firestore.get_action_items_for_overall_score(&user.uid)
    );

    // Calculate daily score
    let daily = match daily_result {
        Ok((completed, total)) => {
            let score = if total > 0 {
                (completed as f64 / total as f64) * 100.0
            } else {
                0.0
            };
            ScoreData { score, completed_tasks: completed, total_tasks: total }
        }
        Err(e) => {
            tracing::error!("Failed to calculate daily score: {}", e);
            ScoreData { score: 0.0, completed_tasks: 0, total_tasks: 0 }
        }
    };

    // Calculate weekly score
    let weekly = match weekly_result {
        Ok((completed, total)) => {
            let score = if total > 0 {
                (completed as f64 / total as f64) * 100.0
            } else {
                0.0
            };
            ScoreData { score, completed_tasks: completed, total_tasks: total }
        }
        Err(e) => {
            tracing::error!("Failed to calculate weekly score: {}", e);
            ScoreData { score: 0.0, completed_tasks: 0, total_tasks: 0 }
        }
    };

    // Calculate overall score
    let overall = match overall_result {
        Ok((completed, total)) => {
            let score = if total > 0 {
                (completed as f64 / total as f64) * 100.0
            } else {
                0.0
            };
            ScoreData { score, completed_tasks: completed, total_tasks: total }
        }
        Err(e) => {
            tracing::error!("Failed to calculate overall score: {}", e);
            ScoreData { score: 0.0, completed_tasks: 0, total_tasks: 0 }
        }
    };

    // Determine default tab - show the one with highest score
    // If daily has tasks and highest score, show daily
    // Otherwise prefer weekly over overall if scores are equal
    let default_tab = if daily.total_tasks > 0 && daily.score >= weekly.score && daily.score >= overall.score {
        "daily"
    } else if weekly.score >= overall.score {
        "weekly"
    } else {
        "overall"
    }.to_string();

    tracing::info!(
        "Scores for user {}: daily={:.1}% ({}/{}), weekly={:.1}% ({}/{}), overall={:.1}% ({}/{}), default={}",
        user.uid,
        daily.score, daily.completed_tasks, daily.total_tasks,
        weekly.score, weekly.completed_tasks, weekly.total_tasks,
        overall.score, overall.completed_tasks, overall.total_tasks,
        default_tab
    );

    Ok(Json(ScoreResponse {
        daily,
        weekly,
        overall,
        default_tab,
        date: date_str,
    }))
}

/// Build the daily score router
pub fn daily_score_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/daily-score", get(get_daily_score))
        .route("/v1/scores", get(get_scores))
}
