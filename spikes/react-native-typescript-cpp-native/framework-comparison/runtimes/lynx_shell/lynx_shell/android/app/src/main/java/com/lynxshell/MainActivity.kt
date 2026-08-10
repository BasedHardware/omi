package com.lynxshell

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import com.lynxshell.modules.OmiNativeModule
import com.lynxshell.providers.GenericResourceFetcher
import com.lynxshell.providers.TemplateProvider
import com.lynx.tasm.LynxBooleanOption
import com.lynx.tasm.LynxView
import com.lynx.tasm.LynxViewBuilder
import com.lynx.xelement.XElementBehaviors

class MainActivity : Activity() {
    private val bluetoothPermissionRequest = 701

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestBluetoothPermissions()

        val lynxView: LynxView = buildLynxView()
        setContentView(lynxView)
        lynxView.renderTemplateUrl("main.lynx.bundle", "")
    }

    private fun requestBluetoothPermissions() {
        val permissions = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        val missing = permissions.filter {
            checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            requestPermissions(missing.toTypedArray(), bluetoothPermissionRequest)
        }
    }

    private fun buildLynxView(): LynxView {
        val viewBuilder: LynxViewBuilder = LynxViewBuilder()
        viewBuilder.addBehaviors(XElementBehaviors().create())
        viewBuilder.setTemplateProvider(TemplateProvider(this))
        viewBuilder.isEnableGenericResourceFetcher = LynxBooleanOption.TRUE
        viewBuilder.setGenericResourceFetcher(GenericResourceFetcher())
        viewBuilder.registerModule("OmiNativeModule", OmiNativeModule::class.java)
        return viewBuilder.build(this)
    }
}
