package com.lynxshell

import android.app.Activity
import android.os.Bundle
import com.lynxshell.providers.GenericResourceFetcher
import com.lynxshell.providers.TemplateProvider
import com.lynx.tasm.LynxBooleanOption
import com.lynx.tasm.LynxView
import com.lynx.tasm.LynxViewBuilder
import com.lynx.xelement.XElementBehaviors

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        var uri = ""
        uri = if (BuildConfig.DEBUG == true) {
            "http://10.0.2.2:3000/main.lynx.bundle?fullscreen=true"
        } else {
            "main.lynx.bundle"
        }

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

        return viewBuilder.build(this)
    }
}