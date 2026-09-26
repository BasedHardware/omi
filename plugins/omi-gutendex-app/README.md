# Omi Project Gutenberg Classic Books App

An integration app for [Omi](https://github.com/BasedHardware/omi) that provides instant access to 70,000+ free classic books, authors, literary genres, and direct reading formats powered by the public Gutendex API (Project Gutenberg).

## Features

- **Search Classic Literature**: Find classic public domain books and authors with topic and language filtering.
- **Browse by Topic / Genre**: Discover books across genres like Gothic, Science Fiction, Philosophy, Adventure, and Poetry.
- **Format & Download Links**: Get immediate links to read online in HTML, download EPUB, or view plain text versions.
- **Zero Authentication**: Completely open and free.

## Endpoints

- `POST /tools/search_books`: Search books by query, topic, and language.
- `POST /tools/books_by_topic`: Browse classic books by literary topic.
- `POST /tools/book_details`: Get full book details, author dates, and format links.
- `GET /manifest.json`: Omi plugin manifest.
- `GET /.well-known/ai-plugin.json`: OpenAI standard manifest.
- `GET /health`: Service health status.
