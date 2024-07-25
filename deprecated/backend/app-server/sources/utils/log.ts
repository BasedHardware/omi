import chalk from 'chalk';
import { format } from 'date-fns';

export function log(src: any) {
    console.log(chalk.gray(format(Date.now(), 'yyyy-MM-dd HH:mm:ss')), src);
}

export function warn(src: any) {
    console.warn(chalk.gray(format(Date.now(), 'yyyy-MM-dd HH:mm:ss')), src);
}