package com.friend.ios.fgs

import android.content.pm.ServiceInfo
import android.os.Build

/**
 * Android 14+ only clears the [android.content.Context.startForegroundService]
 * timeout when [android.app.Service.startForeground] returns. Catching the
 * failure and calling stopSelf() still crashes the process with
 * ForegroundServiceDidNotStartInTimeException.
 *
 * A rejected typed promotion (location while-in-use, dataSync from the
 * background) must be followed by a successful shortService promotion before
 * stop. shortService needs no runtime permission and is what satisfies the
 * contract. Below API 34 that follow-up is unnecessary.
 */
internal object ForegroundStartContract {
    /** A cold start must first use a type without a background-start prerequisite. */
    fun coldStartType(sdkInt: Int): Int? =
        if (sdkInt >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_SHORT_SERVICE
        } else {
            null // Two-argument startForeground before Android 14.
        }

    fun mustPromoteShortServiceBeforeStop(sdkInt: Int): Boolean =
        sdkInt >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE

    /** Notification.Builder.setSmallIcon rejects 0 before startForeground runs. */
    fun notificationIcon(applicationIcon: Int): Int =
        if (applicationIcon != 0) applicationIcon else android.R.drawable.stat_notify_sync
}
