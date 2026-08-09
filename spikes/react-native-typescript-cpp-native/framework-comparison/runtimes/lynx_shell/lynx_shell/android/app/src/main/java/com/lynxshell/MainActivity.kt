package com.lynxshell

import android.app.Activity
import android.os.Bundle
import com.lynxshell.providers.GenericResourceFetcher
import com.lynxshell.providers.TemplateProvider
import com.lynxshell.modules.OmiNativeModule
import com.lynx.tasm.LynxBooleanOption
import com.lynx.tasm.LynxView
import com.lynx.tasm.LynxViewBuilder
import com.lynx.xelement.XElementBehaviors

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val uri = "main.lynx.bundle"

        val lynxView: LynxView = buildLynxView()
        setContentView(lynxView)

        lynxView.renderTemplateUrl(uri, "")
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