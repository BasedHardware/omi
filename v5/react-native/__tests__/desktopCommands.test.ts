describe('desktop search command bridge', () => {
  beforeEach(() => {
    jest.resetModules();
  });

  test('subscribes to the real macOS native event', () => {
    const remove = jest.fn();
    const addListener = jest.fn(() => ({remove}));
    const module = {addListener: jest.fn(), removeListeners: jest.fn()};
    jest.doMock('react-native', () => ({
      NativeEventEmitter: jest.fn(() => ({addListener})),
      NativeModules: {OmiDesktopCommands: module},
      Platform: {OS: 'macos'},
    }));
    const {subscribeDesktopSearchCommand} = require('../src/desktopCommands');
    const listener = jest.fn();
    const subscription = subscribeDesktopSearchCommand(listener);

    expect(addListener).toHaveBeenCalledWith('desktopSearchCommand', listener);
    subscription.remove();
    expect(remove).toHaveBeenCalledTimes(1);
  });

  test('is inert outside macOS and without the native module', () => {
    const NativeEventEmitter = jest.fn();
    jest.doMock('react-native', () => ({
      NativeEventEmitter,
      NativeModules: {},
      Platform: {OS: 'ios'},
    }));
    const {subscribeDesktopSearchCommand} = require('../src/desktopCommands');
    expect(() =>
      subscribeDesktopSearchCommand(jest.fn()).remove(),
    ).not.toThrow();
    expect(NativeEventEmitter).not.toHaveBeenCalled();
  });
});
