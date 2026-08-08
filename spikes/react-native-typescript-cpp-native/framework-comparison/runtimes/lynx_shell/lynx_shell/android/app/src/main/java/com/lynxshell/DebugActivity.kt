package com.lynxshell

import android.app.Activity
import android.os.Bundle
import com.lynxshell.providers.TemplateProvider
import com.lynx.tasm.LynxView
import com.lynx.tasm.LynxViewBuilder
import com.lynx.tasm.TemplateData

class DebugActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val lynxView = buildLynxView()
        setContentView(lynxView)
        val url = intent.getStringExtra("url")
        if (url != null) {
            lynxView.renderTemplateUrl(url, TemplateData.empty())
        }
    }

    private fun buildLynxView(): LynxView {
        val viewBuilder = LynxViewBuilder()
        viewBuilder.setTemplateProvider(TemplateProvider(this))
        return viewBuilder.build(this)
    }
}