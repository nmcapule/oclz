import argparse
import configparser
import logging
import os
import sys

from sync import sync

DEFAULT_CONFIG_PATH = "configs/config.ini"


def ReadConfig(filename):
    """Reads and returns the ConfigParser instance."""
    config = configparser.RawConfigParser()
    config.read(os.path.join(os.path.abspath(os.path.dirname(__file__)), filename))
    return config


def CommandSync(config, args):
    """Cleanup and do syncing of products."""
    sync.DoCleanupProcedure(config)
    sync.DoSyncProcedure(config)


def CommandReauthenticate(config, args):
    """Refresh authentication token."""
    DoLazadaResetAccessToken(config, args.token)


def CommandCleanup(config, args):
    """Cleanup dangling data."""
    sync.DoCleanupProcedure(config)


def CommandCheckConfig(config, args):
    """Check if auth config is still working."""
    logging.info(config.sections())
    oauth2_service = sync.Oauth2Service()
    with oauth2_service:
        lazada_oauth2_dict = oauth2_service.GetOauth2Tokens(sync._SYSTEM_LAZADA)
        logging.info(lazada_oauth2_dict)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Command name to function mapping.
    COMMAND_LOOKUP = {
        "sync": CommandSync,
        "lzreauth": CommandReauthenticate,
        "cleanup": CommandCleanup,
        "chkconfig": CommandCheckConfig,
    }

    # Setup argument parser.
    parser = argparse.ArgumentParser(
        description="Opencart-Lazada-Shopee syncing script."
    )
    parser.add_argument(
        "mode",
        choices=COMMAND_LOOKUP.keys(),
        action="store",
        help="OCLZSH syncing script mode",
    )
    parser.add_argument(
        "--config",
        action="store",
        default=os.getenv("CONFIG_PATH", DEFAULT_CONFIG_PATH),
        help="path of the config file",
    )
    parser.add_argument(
        "--token",
        action="store",
        default="",
        help="token to use when reauthenticating to Lazada",
    )
    args = parser.parse_args(sys.argv[1:])

    # Setup config path.
    config = ReadConfig(args.config)

    # Invoke action based on matching mode.
    COMMAND_LOOKUP[args.mode](config, args)
