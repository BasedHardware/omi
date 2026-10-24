package com.friend.ios.service.stores

/** Port of `Paging.swift`. */
internal object Paging {
    /** Fetches pages until one comes back short. [maxPages] guards against a backend that ignores `offset`. */
    suspend fun <Item> all(pageSize: Int, maxPages: Int = 100, fetch: suspend (limit: Int, offset: Int) -> List<Item>): List<Item> {
        val items = mutableListOf<Item>()
        repeat(maxPages) {
            val page = fetch(pageSize, items.size)
            items += page
            if (page.size < pageSize) return items
        }
        return items
    }
}
