#!/bin/bash -x
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
#
# !!!IMPORTANT!!!
# Edit this file and change this next line to your own email address:
#

EMAIL="chris.clearfield@gmail.com"

# Upgrade and install Postfix so we can send a sample email
export DEBIAN_FRONTEND=noninteractive

apt-add-repository multiverse 
apt-get update && apt-get upgrade -y && apt-get install -y postfix

# Pythonic stuff
apt-get install -y unzip python-dev python-pip ec2-api-tools

cd /root
wget https://github.com/clearf/cal-tracker/archive/master.zip
unzip master.zip
cd cal-tracker-master/
pip install -r requirements.txt


# Get some information about the running instance
instance_id=$(wget -qO- instance-data/latest/meta-data/instance-id)
public_ip=$(wget -qO- instance-data/latest/meta-data/public-ipv4)
zone=$(wget -qO- instance-data/latest/meta-data/placement/availability-zone)
egion=$(expr match $zone '\(.*\).')
uptime=$(uptime)


# Attach /data
ec2-attach-volume --region us-west-2 -i $instance_id -d /dev/sdh vol-a3f4a9a6

sleep 20

mkdir /data
mount /dev/sdh /data

output=$(python -m app.google.google_client)

# Send status email
/usr/sbin/sendmail -oi -t -f $EMAIL <<EOM
From: $EMAIL
To: $EMAIL
Subject: Ran process in autoscaling

Output: $output

This email message was generated on the following EC2 instance:

  instance id: $instance_id
  region:      $region
  public ip:   $public_ip
  uptime:      $uptime

If the instance is still running, you can monitor the output of this
job using a command like:

  ssh ubuntu@$public_ip tail -1000f /var/log/user-data.log


For more information about this demo:

  Running EC2 Instances on a Recurring Schedule with Auto Scaling
  http://alestic.com/2011/11/ec2-schedule-instance

EOM

# This will stop the EBS boot instance, stopping the hourly charges.
# Have Auto Scaling terminate it, stopping the storage charges.
# Give the email some time to be queued and delivered

sleep 300 # 5 minutes
shutdown -h now

exit 0

########################################################################
#
# For more information about this code, please read:
#
#   Running EC2 Instances on a Recurring Schedule with Auto Scaling
#   http://alestic.com/2011/11/ec2-schedule-instance
#
# The code and its license are available on github:
#
#   https://github.com/alestic/demo-ec2-schedule-instance
#
########################################################################
