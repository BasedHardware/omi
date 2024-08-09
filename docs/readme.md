# How to test locally

## Prerequisites

Follow the [instructions](https://docs.github.com/en/pages/setting-up-a-github-pages-site-with-jekyll/testing-your-github-pages-site-locally-with-jekyll) how to install Ruby, Bundler, and Jekyll.

Note: On Windows, the easiest way is install the prerequisites and do testing in WSL.

## Run the site locally

```bash
bundle exec jekyll serve --incremental --watch --force_polling --open-
url --livereload
```
