"""Hourly scheduler entrypoint: bounded content-free cleanup, no provider construction."""

import argparse
import logging
import os

from database.messaging import MessagingStore


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-launch', action='store_true')
    args = parser.parse_args()
    if args.prepare_launch:
        counts = MessagingStore().prepare_launch()
        logging.getLogger(__name__).info('Messaging launch metadata counts=%s', counts)
        return
    days = int(os.getenv('OMI_MESSAGING_RETENTION_DAYS', '30'))
    if days < 7:
        raise ValueError('Messaging retention must be at least seven days')
    counts = MessagingStore().cleanup(retention_days=days)
    logging.getLogger(__name__).info('Messaging maintenance counts=%s', counts)


if __name__ == '__main__':
    main()
