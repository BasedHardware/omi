import * as fs from 'fs';
import * as path from 'path';
import * as progress from 'cli-progress';
import { imageDescription } from '../sources/agent/imageDescription';
import { imageBlurry } from '../sources/agent/imageBlurry';

(async () => {

    let imageTests: { path: string, image: Buffer, outputs: string }[] = [];

    // Read all directories
    let allFiles = fs.readdirSync(__dirname);
    for (let f of allFiles) {
        if (fs.statSync(path.join(__dirname, f)).isDirectory()) {
            console.log(`Run series ${f}`);
            let files = fs.readdirSync(path.join(__dirname, f));
            for (let s of files) {
                if (s.endsWith('.jpeg')) {
                    let image = fs.readFileSync(path.join(__dirname, f, s));
                    imageTests.push({ path: path.join(__dirname, f, s).replace('.jpeg', '.md'), image, outputs: '' });
                }
            }
        }
    }

    async function runTest(title: string, test: (img: Uint8Array) => Promise<string>) {
        console.log(`Run ${title}`);
        let bar = new progress.SingleBar({}, progress.Presets.shades_classic);
        bar.start(imageTests.length, 0);
        for (let i = 0; i < imageTests.length; i++) {
            let o = await test(imageTests[i].image);
            imageTests[i].outputs += '####' + title + '####\n';
            imageTests[i].outputs += o + '\n';
            bar.increment();
        }
        bar.stop();
    }

    // Run tests
    await runTest('Description', async (img) => {
        return await imageDescription(img);
    });
    await runTest('Description (llava-llama3)', async (img) => {
        return await imageDescription(img, 'llava-llama3');
    });
    await runTest('Description (llava:34b-v1.6)', async (img) => {
        return await imageDescription(img, 'llava:34b-v1.6');
    });
    await runTest('Description (moondream:1.8b-v2-fp16)', async (img) => {
        return await imageDescription(img, 'moondream:1.8b-v2-fp16');
    });

    // console.log(`Run blurry tests`);
    // for (let i of imageTests) {
    //     i.outputs += '####Blurry####\n';
    //     i.outputs += await imageBlurry(i.image) + '\n';
    // }

    // Write outputs
    for (let i of imageTests) {
        fs.writeFileSync(i.path, i.outputs);
    }
})();