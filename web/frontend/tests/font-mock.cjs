// No font network calls in the synthetic HTTP contract test.
module.exports = new Proxy(
  {},
  {
    get: () => "@font-face { font-family: 'Synthetic'; src: local('Arial'); }",
  },
);
