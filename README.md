
# Overview

This little script hack collects data from one or more ISKRA MT681-D4A51-K0p power meterss using the optic interface and sends the data to a 
local zabbix-proxy instance.

I used the following hardware:

* 2 ISKRA MT681-D4A51-K0p Power Meters
* A Raspberry PI with Raspbian GNU/Linux 10
* 2 expensive [Weidmann USB optic sensors](https://shop.weidmann-elektronik.de/index.php?page=product&info=24])</br>
  (i was to lazy to solder two sensor by my own, unbelievable price for such a simple hardware :-)


For details of the monitored kubernetes attributes, have a look at the [documentation](http://htmlpreview.github.io/?https://github.com/scoopex/zabbix-sml-collector/blob/master/template/documentation/custom_hw_building_template.html)

# Installation and usage


* Install
  ```
  cd /opt
  git clone git@github.com:scoopex/zabbix-sml-collector.git
  cd zabbix-sml-collector
  apt-get install python3-pip -y
  pip3 install -Ur requirements.txt
  ```
* Test
  ```
  ./sml_collector.py
  ```
* Install as service
  ```
  cp sml_collector.service /etc/systemd/system/sml_collector.service
  chown root:root /etc/systemd/system/sml_collector.service
  systemctl daemon-reload
  systemctl enable sml_collector.service
  systemctl start csml_collector.service
  systemctl status sml_collector.service
  ```
* Add zabbix template from `zabbix/custom_hw_building_template.xml`

# Authors
  * Marc Schoechlin <ms-github@256bit.org>
