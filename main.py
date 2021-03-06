import logging
import sys
import time

import click

from autoscaler.cluster import Cluster
from autoscaler.notification import Notifier

logger = logging.getLogger('autoscaler')

DEBUG_LOGGING_MAP = {
    0: logging.CRITICAL,
    1: logging.WARNING,
    2: logging.INFO,
    3: logging.DEBUG
}

class MultimapParamType(click.ParamType):
    """A multimap parameter type. Multiple entries are separated by commas (,),
    and keys are separated from values by equals (=). Map values are sets of
    all values given for the same key.
    """

    name = 'dict'

    def convert(self, value, param, ctx):
        result = {}

        if not value:
            return result

        entry_list = value.split(',')
        for entry in entry_list:
            try:
                entry_key, entry_value = entry.split('=')
                if entry_key not in result:
                    result[entry_key] = set()
                result[entry_key].add(entry_value)
            except ValueError:
                self.fail('%s is not a key=value pair' % value, param, ctx)
        return result

MULTIMAP_PARAM = MultimapParamType()

@click.command()
@click.option("--cluster-name")
@click.option("--regions", default="us-west-1")
@click.option("--sleep", default=60)
@click.option("--kubeconfig", default=None,
              help='Full path to kubeconfig file. If not provided, '
                   'we assume that we\'re running on kubernetes.')
@click.option("--pod-namespace", default=None,
              help='The namespace to look for out-of-resource pods in. By '
                   'default, this will look in all namespaces.')
@click.option("--idle-threshold", default=3600)
@click.option("--type-idle-threshold", default=3600*24*7)
@click.option("--over-provision", default=5)
@click.option("--aws-access-key", default=None, envvar='AWS_ACCESS_KEY_ID')
@click.option("--aws-secret-key", default=None, envvar='AWS_SECRET_ACCESS_KEY')
@click.option("--datadog-api-key", default=None, envvar='DATADOG_API_KEY')
@click.option("--instance-init-time", default=25 * 60)
@click.option("--no-scale", is_flag=True)
@click.option("--no-maintenance", is_flag=True)
@click.option("--slack-hook", default=None, envvar='SLACK_HOOK',
              help='Slack webhook URL. If provided, post scaling messages '
                   'to Slack.')
@click.option("--slack-bot-token", default=None, envvar='SLACK_BOT_TOKEN',
              help='Slack bot token. If provided, post scaling messages '
                   'to Slack users directly.')
@click.option("--dry-run", is_flag=True)
@click.option('--verbose', '-v',
              help="Sets the debug noise level, specify multiple times "
                   "for more verbosity.",
              type=click.IntRange(0, 3, clamp=True),
              count=True)
@click.option('--drainable-labels', default='', type=MULTIMAP_PARAM,
              help='Label keys and values that will be considered drainable when '
                   'scaling down a node. This should be a comma-separated key=value '
                   'list.')
@click.option("--scale-label", default=None)
@click.option('--instance-type-priorities', default='', type=MULTIMAP_PARAM,
              help='This should be a comma-separated key=value list. '
                   'ASGs with instance types that have priorities closer to 0 will '
                   'get scaled up first.')
def main(cluster_name, regions, sleep, kubeconfig, pod_namespace,
         aws_access_key, aws_secret_key, datadog_api_key,
         idle_threshold, type_idle_threshold,
         over_provision, instance_init_time, no_scale, no_maintenance,
         slack_hook, slack_bot_token, dry_run, verbose, drainable_labels, scale_label,
         instance_type_priorities):
    logger_handler = logging.StreamHandler(sys.stderr)
    logger_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(logger_handler)
    logger.setLevel(DEBUG_LOGGING_MAP.get(verbose, logging.CRITICAL))

    if not (aws_secret_key and aws_access_key):
        logger.error("Missing AWS credentials. Please provide aws-access-key and aws-secret-key.")
        sys.exit(1)

    notifier = Notifier(slack_hook, slack_bot_token)
    cluster = Cluster(aws_access_key=aws_access_key,
                      aws_secret_key=aws_secret_key,
                      regions=regions.split(','),
                      kubeconfig=kubeconfig,
                      pod_namespace=pod_namespace,
                      idle_threshold=idle_threshold,
                      instance_init_time=instance_init_time,
                      type_idle_threshold=type_idle_threshold,
                      cluster_name=cluster_name,
                      scale_up=not no_scale,
                      maintainance=not no_maintenance,
                      over_provision=over_provision,
                      datadog_api_key=datadog_api_key,
                      notifier=notifier,
                      dry_run=dry_run,
                      drainable_labels=drainable_labels,
                      scale_label=scale_label,
                      instance_type_priorities=instance_type_priorities
                      )
    backoff = sleep
    while True:
        scaled = cluster.scale_loop()
        if scaled:
            time.sleep(sleep)
            backoff = sleep
        else:
            logger.warn("backoff: %s" % backoff)
            backoff *= 2
            time.sleep(backoff)


if __name__ == "__main__":
    main()
