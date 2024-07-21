import { whisper } from "./inference";

describe('inference', () => {
    it('should return text', async () => {
        let output = await whisper('https://github.com/ex3ndr/facodec/raw/master/eval/eval_0.wav');
        expect(output).toBe('But the affair was magnified as a crowning proof that the free state men were insurrectionist and outlaws.');
    });
})