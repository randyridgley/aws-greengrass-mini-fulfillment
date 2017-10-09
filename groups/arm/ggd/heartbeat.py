#!/usr/bin/env python

# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not
# use this file except in compliance with the License. A copy of the License is
# located at
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

import os
import json
import time
import random
import socket
import argparse
import datetime
import logging

import ggd_config

from AWSIoTPythonSDK.core.greengrass.discovery.providers import \
    DiscoveryInfoProvider
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient, DROP_OLDEST
from mqtt_utils import mqtt_connect, ggc_discovery
from gg_group_setup import GroupConfigFile

dir_path = os.path.dirname(os.path.realpath(__file__))
heartbeat_topic = '/heart/beat'

log = logging.getLogger('heartbeat')
handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s|%(name)-8s|%(levelname)s: %(message)s')
handler.setFormatter(formatter)
log.addHandler(handler)
log.setLevel(logging.INFO)


def heartbeat(device_name, config_file, root_ca, certificate, private_key,
              group_ca_dir, topic):
    # read the config file
    cfg = GroupConfigFile(config_file)

    # determine heartbeat device's thing name and orient MQTT client to GG Core
    heartbeat_name = cfg['devices'][device_name]['thing_name']
    iot_endpoint = cfg['misc']['iot_endpoint']

    # Discover Greengrass Core
    dip = DiscoveryInfoProvider()
    dip.configureEndpoint(iot_endpoint)
    dip.configureCredentials(
        caPath=root_ca, certPath=certificate, keyPath=private_key
    )
    dip.configureTimeout(10)  # 10 sec
    log.info("Discovery using CA: {0} certificate: {1} prv_key: {2}".format(
        root_ca, certificate, private_key
    ))
    discovered, group_list, core_list, group_ca, ca_list = ggc_discovery(
        heartbeat_name, dip, group_ca_dir, retry_count=10
    )

    if discovered is False:
        log.error(
            "Discovery failed for: {0} when connecting to "
            "service endpoint: {1}".format(
                heartbeat_name, iot_endpoint
            ))
        return
    log.info("Discovery success, core_list[0]:{0}".format(core_list[0]))

    # Greengrass Core discovered, now connect to Core from this GG Device
    mqttc = AWSIoTMQTTClient(heartbeat_name)
    mqttc.configureCredentials(group_ca, private_key, certificate)
    mqttc.configureOfflinePublishQueueing(10, DROP_OLDEST)

    core_info = core_list[0]
    if mqtt_connect(mqtt_client=mqttc, core_info=core_info):
        # MQTT client has connected to GG Core, start heartbeat messages
        try:
            start = datetime.datetime.now()
            hostname = socket.gethostname()
            while True:
                now = datetime.datetime.now()
                msg = {
                    "version": "2017-07-05",  # YYYY-MM-DD
                    "ggd_id": heartbeat_name,
                    "hostname": hostname,
                    "data": [
                        {
                            "sensor_id": "heartbeat",
                            "ts": now.isoformat(),
                            "duration": str(now - start)
                        }
                    ]
                }
                print("[hb] publishing heartbeat msg: {0}".format(msg))
                mqttc.publish(topic, json.dumps(msg), 0)
                time.sleep(random.random() * 10)

        except KeyboardInterrupt:
            log.info(
                "[hb] KeyboardInterrupt ... exiting heartbeat")
        mqttc.disconnect()
        time.sleep(2)
    else:
        print("[hb] could not connect successfully to: {0} via mqtt.".format(
            core_info
        ))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Greengrass device that generates heartbeat messages',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('device_name',
                        help="The heartbeat's GGD device_name.")
    parser.add_argument('config_file',
                        help="The config file.")
    parser.add_argument('root_ca',
                        help="Root CA File Path of Server Certificate.")
    parser.add_argument('certificate',
                        help="File Path of GGD Certificate.")
    parser.add_argument('private_key',
                        help="File Path of GGD Private Key.")
    parser.add_argument('group_ca_dir',
                        help="The directory where the discovered Group CA will "
                             "be saved.")
    parser.add_argument('--topic', default=heartbeat_topic,
                        help="Topic used to communicate heartbeat telemetry.")
    parser.add_argument('--frequency', default=3,
                        help="Frequency in seconds to send heartbeat messages.")

    args = parser.parse_args()
    heartbeat(
        device_name=args.device_name,
        config_file=args.config_file, root_ca=args.root_ca,
        certificate=args.certificate, private_key=args.private_key,
        group_ca_dir=args.group_ca_dir, topic=args.topic
    )
