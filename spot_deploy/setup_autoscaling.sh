ami_id=ami-5189a661 # Ubuntu 14.04 generic server
region=us-west-2    # Region for running the demo

zone=${region}b     # A zone in that region
export EC2_URL=https://$region.ec2.amazonaws.com
export AWS_AUTO_SCALING_URL=https://autoscaling.$region.amazonaws.com
launch_config=cal-tracker
auto_scale_group=cal-tracker-autoscale


# ec2-run-instances   --region us-west-2 -z us-west-2b --instance-type t2.micro -p cal-tracker-config  -k mbp -g ssh-open --instance-initiated-shutdown-behavior terminate  --user-data-file spot_deploy/update_schedule.sh $ami_id

as-create-launch-config -k mbp -g ssh-open -p cal-tracker-config \
  --instance-type t2.micro --image-id $ami_id --launch-config $launch_config

as-create-auto-scaling-group \
    --auto-scaling-group "$auto_scale_group" \
    --launch-configuration "$launch_config" \
    --availability-zones "$zone" \
    --min-size 0 \
    --max-size 0

# Don't replace unhealty processes
as-suspend-processes "$auto_scale_group" --processes ReplaceUnhealthy

# UTC: 1:00, 7:00, 13:00, 19:00
as-put-scheduled-update-group-action \
    --name "cal-tracker-schedule-start" \
    --auto-scaling-group "$auto_scale_group" \
    --min-size 1 \
    --max-size 1 \
    --recurrence "0 05,11,17,23 * * *"

as-put-scheduled-update-group-action \
    --name "cal-tracker-schedule-stop" \
    --auto-scaling-group "$auto_scale_group" \
    --min-size 0 \
    --max-size 0 \
    --recurrence "55 05,11,17,23 * * *"



