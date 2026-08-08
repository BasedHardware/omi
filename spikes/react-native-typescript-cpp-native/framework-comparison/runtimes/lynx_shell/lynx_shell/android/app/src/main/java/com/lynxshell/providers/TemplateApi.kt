package com.lynxshell.providers

import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.Call
import retrofit2.http.Body
import retrofit2.http.FieldMap
import retrofit2.http.GET
import retrofit2.http.HeaderMap
import retrofit2.http.POST
import retrofit2.http.Url

interface TemplateApi {
    @GET
    fun getTemplate(@Url u: String?): Call<ResponseBody>

    @GET
    fun get(@Url url: String?, @HeaderMap headers: Map<String?, String?>?): Call<ResponseBody?>?

    @POST
    fun postForm(
        @Url url: String?, @FieldMap fields: Map<String?, String?>?,
        @HeaderMap headers: Map<String?, String?>?
    ): Call<ResponseBody?>?

    @POST
    fun postData(
        @Url url: String?, @Body data: RequestBody?, @HeaderMap headers: Map<String?, String?>?
    ): Call<ResponseBody?>?
}
