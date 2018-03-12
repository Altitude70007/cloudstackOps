#!/usr/bin/python

import getopt
import getpass
import os.path
import sys
import time
from datetime import datetime

from cloudstackops import cloudstackops
from cloudstackops import cloudstacksql
from cloudstackops import kvm
from cloudstackops import vmware


class migrateVirtualMachineFromVMwareToKVM():
    def __init__(self):
        # Input parameters
        self.DEBUG = 0
        self.DRYRUN = 1
        self.instancename = ''
        self.toCluster = ''
        self.configProfileName = ''
        self.force = 0
        self.threads = 5
        self.mysqlHost = ''
        self.mysqlPasswd = ''
        self.newBaseTemplate = ''
        self.helperScriptsPath = None
        self.startVM = True
        self.esxiHost = ''
        self.vmxPath = ''
        self.serviceOffering = ''
        self.networkIp = ''
        self.zone = ''
        self.domain = ''
        self.account = ''

        self.cosmic = None
        self.sql = None

        self.kvm_host = None
        self.disk_sizes = {}
        self.disk_name = ''

    # Function to handle our arguments
    def handleArguments(self, argv):

        # Usage message
        help = "Usage: ./" + os.path.basename(__file__) + ' [options] ' + \
               '\n  --config-profile -c <profilename>\t\t\t\t\tSpecify the CloudMonkey profile name to get the credentials from ' \
               '(or specify in ./config file)' + \
               '\n  --instance-name -i <instancename>\t\t\t\t\tMigrate VM with this instance name' + \
               '\n  --esxi-host -e <ipv4 address>\t\t\t\t\t\tMigrate VM from this esxi host' + \
               '\n  --vmx-path -v <vmxpath>\t\t\t\t\t\t\tThe vmx path including /vmfs/volumes/' + \
               '\n  --to-cluster -t <clustername>\t\t\t\t\t\tMigrate VM to this cluster' + \
               '\n  --service-offering -o <serviceoffering>\t\t\tThe serviceoffering of the VM' + \
               '\n  --network-ip -n <ip1,network1,ip2,network2,....>\tThe network config of the new vm' + \
               '\n  --zone -z <zone name>\t\t\t\t\t\t\t\tThe zone name of the new vm' + \
               '\n  --account -a <account name>\t\t\t\t\t\tThe account name of the new vm' + \
               '\n  --domain -d <domain name>\t\t\t\t\t\t\tThe domain name of the new vm' + \
               '\n  --new-base-template -b <template>\t\t\t\t\tKVM template to link the VM to. Won\'t do much, mostly needed for ' \
               'properties like tags. We need to record it in the DB as it cannot be NULL' + \
               '\n  --mysqlserver -s <mysql hostname>\t\t\t\t\tSpecify MySQL server config section name' + \
               '\n  --mysqlpassword <passwd>\t\t\t\t\t\t\tSpecify password to cloud ' + \
               'MySQL user' + \
               '\n  --start-vm\t\t\t\t\t\t\t\t\t\tStart VM when migration is complete; default=true' + \
               '\n  --helper-scripts-path\t\t\t\t\t\t\t\tFolder with scripts to be copied to hypervisor in migrate working folder' + \
               '\n  --debug\t\t\t\t\t\t\t\t\t\t\tEnable debug mode' + \
               '\n  --exec\t\t\t\t\t\t\t\t\t\t\tExecute for real' + \
               '\n\n\n\n' + \
               '\nMake sure the esxi host is in the known hosts file of every kvm host in the cluster ' \
               'for h in 01 02 03 04 05 06 07 08 09 10 11 12 13 14; do ssh mccppod051-hv${h} -A "sudo -E ssh -o StrictHostKeyChecking=no root@172.16.98.219 ls"; done"; done'

        try:
            opts, args = getopt.getopt(
                argv,
                "hc:i:t:p:s:b:v:e:o:n:z:a:d:",
                [
                    "config-profile=", "instance-name=", "to-cluster=", "esxi-host=", "vmx-path=", "mysqlserver=",
                    "mysqlpassword=", "zone=", "account=", "domain=", "new-base-template=", "start-vm",
                    "helper-scripts-path=", "debug", "exec", "force", "service-offering=", "network-ip="]
            )
        except getopt.GetoptError as e:
            print "Error: " + str(e)
            print help
            sys.exit(2)
        for opt, arg in opts:
            if opt == '-h':
                print help
                sys.exit()
            elif opt in ("-c", "--config-profile"):
                self.configProfileName = arg
            elif opt in ("-i", "--instance-name"):
                self.instancename = arg
            elif opt in ("-t", "--to-cluster"):
                self.toCluster = arg
            elif opt in ("-e", "--esxi-host"):
                self.esxiHost = arg
            elif opt in ("-v", "--vmx-path"):
                self.vmxPath = arg
            elif opt in ("-o", "--service-offering"):
                self.serviceOffering = arg
            elif opt in ("-n", "--network-ip"):
                self.networkIp = arg
            elif opt in ("-z", "--zone"):
                self.zone = arg
            elif opt in ("-d", "--domain"):
                self.domain = arg
            elif opt in ("-a", "--account"):
                self.account = arg
            elif opt in ("-b", "--new-base-template"):
                self.newBaseTemplate = arg
            elif opt in ("-s", "--mysqlserver"):
                self.mysqlHost = arg
            elif opt in ("-p", "--mysqlpassword"):
                self.mysqlPasswd = arg
            elif opt in ("--debug"):
                self.DEBUG = 1
            elif opt in ("--exec"):
                self.DRYRUN = 0
            elif opt in ("--force"):
                self.force = 1
            elif opt in ("--start-vm"):
                self.startVM = True
            elif opt in ("--helper-scripts-path"):
                self.helperScriptsPath = arg

        # Default to cloudmonkey default config file
        if len(self.configProfileName) == 0:
            self.configProfileName = "config"

        # We need at least these vars
        if len(self.instancename) == 0 or \
                len(self.toCluster) == 0 or \
                len(self.mysqlHost) == 0 or \
                len(self.vmxPath) == 0 or \
                len(self.esxiHost) == 0 or \
                len(self.serviceOffering) == 0 or \
                len(self.networkIp) == 0 or \
                len(self.zone) == 0 or \
                len(self.domain) == 0 or \
                len(self.account) == 0:
            print help
            sys.exit()

        # if not os.path.isdir(helperScriptsPath):
        #     print "Error: Directory %s as specified with --helper-scripts-path does not exist!" % helperScriptsPath
        #     sys.exit(1)

    def migrate(self):
        # First handle the arguments!
        self.handleArguments(sys.argv[1:])

        # Start time
        print "Note: Starting @ %s" % time.strftime("%Y-%m-%d %H:%M")

        if self.DEBUG == 1:
            print "Warning: Debug mode is enabled!"

        if self.DRYRUN == 1:
            print "Warning: dry-run mode is enabled, not running any commands!"

        # Init classes
        self.init_classes()

        # Verify input
        self.verify_input()

        # Configure kvm -> choose host / storage pool
        # self.prepare_kvm()

        # Do virt-v2v migration
        # self.vmware_virt_v2v()

        # Gather disk info
        self.gather_disk_info()

        # Deploy the vm
        # self.deploy_vm()

        # Add extra data disks
        self.add_data_disks()

    def exit_script(self, message):
        print "Fatal Error: %s" % message
        sys.exit(1)

    # def start_vm(self, hypervisor_name, start=startVM):
    #     global message, result
    #     if self.DRYRUN == 1:
    #         message = "Would have started vm %s with id %s" % (vm.name, vm.id)
    #         c.print_message(message=message, message_type="Note", to_slack=False)
    #     elif start:
    #         message = "Starting virtualmachine %s with id %s" % (vm.name, vm.id)
    #         c.print_message(message=message, message_type="Note", to_slack=True)
    #         result = c.startVirtualMachine(vm.id)
    #         if result == 1:
    #             message = "Start vm failed -- exiting."
    #             c.print_message(message=message, message_type="Error", to_slack=True)
    #             message = "investegate manually!"
    #             c.print_message(message=message, message_type="Note", to_slack=False)
    #             sys.exit(1)
    #
    #         if result.virtualmachine.state == "Running":
    #             message = "%s is started successfully on %s" % (result.virtualmachine.name, hypervisor_name)
    #             c.print_message(message=message, message_type="Note", to_slack=True)
    #         else:
    #             warningMsg = "Warning: " + result.virtualmachine.name + " is in state " + \
    #                          result.virtualmachine.state + \
    #                          " instead of Running. Please investigate (could just take some time)."
    #             print warningMsg

    def init_classes(self):
        # Init CloudStackOps class
        self.cosmic = cloudstackops.CloudStackOps(self.DEBUG, self.DRYRUN)
        self.cosmic.task = "VMware -> KVM migration"
        self.cosmic.slack_custom_title = "Migration details"

        # Init VMware class
        v = vmware.vmware('root', self.threads)
        v.DEBUG = self.DEBUG
        v.DRYRUN = self.DRYRUN
        self.cosmic.vmware = v

        # Init KVM class
        k = kvm.Kvm(ssh_user=getpass.getuser(), threads=self.threads, helper_scripts_path=self.helperScriptsPath)
        k.DEBUG = self.DEBUG
        k.DRYRUN = self.DRYRUN
        self.cosmic.kvm = k

        # Init SQL class
        self.sql = cloudstacksql.CloudStackSQL(self.DEBUG, self.DRYRUN)

        # Connect MySQL
        result = self.sql.connectMySQL(self.mysqlHost, self.mysqlPasswd)
        if result > 0:
            message = "MySQL connection failed"
            self.cosmic.print_message(message=message, message_type="Error", to_slack=True)
            sys.exit(1)
        elif self.DEBUG == 1:
            print "DEBUG: MySQL connection successful"
            print self.sql.conn

        # make credentials file known to our class
        self.cosmic.configProfileName = self.configProfileName

        # Init the Cosmic API
        self.cosmic.initCloudStackAPI()

        if self.DEBUG == 1:
            print "API address: " + self.cosmic.apiurl
            print "ApiKey: " + self.cosmic.apikey
            print "SecretKey: " + self.cosmic.secretkey

        # Check cloudstack IDs
        if self.DEBUG == 1:
            print "Debug: Checking CloudStack IDs of provided input.."

        self.cosmic.slack_custom_title = "Migration details for vmx %s" % self.vmxPath

    def verify_input(self):
        # Check domain of the new vm
        domainID = self.cosmic.checkCloudStackName({'csname': self.domain, 'csApiCall': 'listDomains'})

        self.verify_checked_cosmic_name('Domain', domainID)

        message = "Domain ID found for %s is %s" % (self.domain, domainID)
        self.cosmic.print_message(message=message, message_type="Note", to_slack=False)
        self.domain = domainID

        # Check cust domain of the new vm
        custDomainID = self.cosmic.checkCloudStackName({'csname': 'Cust', 'csApiCall': 'listDomains'})

        self.verify_checked_cosmic_name('Domain', custDomainID)

        message = "Domain ID found for Cust is %s" % (custDomainID)
        self.cosmic.print_message(message=message, message_type="Note", to_slack=False)

        # Check cluster name
        toClusterID = self.cosmic.checkCloudStackName({'csname': self.toCluster, 'csApiCall': 'listClusters'})

        self.verify_checked_cosmic_name('Cluster', toClusterID)

        message = "Cluster ID found for %s is %s" % (self.toCluster, toClusterID)
        self.cosmic.print_message(message=message, message_type="Note", to_slack=False)
        self.cosmic.cluster = toClusterID
        self.toCluster = toClusterID

        # Check template
        if len(self.newBaseTemplate) == 0:
            print "Please specify a template one using the --new-base-template " \
                  "flag and try again. Using 'Linux - Unknown template converted from XenServer'"
            self.newBaseTemplate = 'Linux - Unknown template converted from XenServer'

        templateID = self.cosmic.checkCloudStackName({'csname': self.newBaseTemplate, 'csApiCall': 'listTemplates'})

        self.verify_checked_cosmic_name('Template', templateID)

        message = "Template ID found for %s is %s" % (self.newBaseTemplate, templateID)
        self.cosmic.print_message(message=message, message_type="Note", to_slack=False)
        self.newBaseTemplate = templateID

        # Check service offering of the new vm
        serviceOfferingID = self.cosmic.checkCloudStackName(
            {'csname': self.serviceOffering, 'csApiCall': 'listServiceOfferings', 'domainid': custDomainID})

        self.verify_checked_cosmic_name('Service Offering', serviceOfferingID)

        message = "Service offering ID found for %s is %s" % (self.serviceOffering, serviceOfferingID)
        self.cosmic.print_message(message=message, message_type="Note", to_slack=False)
        self.serviceOffering = serviceOfferingID

        # Check zone of the new vm
        zoneID = self.cosmic.checkCloudStackName({'csname': self.zone, 'csApiCall': 'listZones'})

        self.verify_checked_cosmic_name('Zone', zoneID)

        message = "Zone ID found for %s is %s" % (self.zone, zoneID)
        self.cosmic.print_message(message=message, message_type="Note", to_slack=False)
        self.zone = zoneID

        networkIpList = self.networkIp.split(',')
        self.networkIp = []

        x = 0
        while x < len(networkIpList):
            network = networkIpList[x + 1]

            # Check network of the new vm
            networkID = self.cosmic.checkCloudStackName(
                {'csname': network, 'csApiCall': 'listNetworks', 'listAll': 'true'})

            self.verify_checked_cosmic_name('Network', networkID)

            message = "Network ID found for %s is %s" % (network, networkID)
            self.cosmic.print_message(message=message, message_type="Note", to_slack=False)

            self.networkIp.append({
                'ip': networkIpList[x],
                'networkid': networkID
            })
            x += 1
            x += 1

    def verify_checked_cosmic_name(self, type, id):
        if id == 1 or id is None:
            message = "Cosmic type '%s' with name '%s' can not be found! Halting!" % (type, id)
            self.cosmic.print_message(message=message, message_type="Error", to_slack=False)
            sys.exit(1)

    def prepare_kvm(self):
        # Get cluster hosts
        self.kvm_host = self.cosmic.getRandomHostFromCluster(self.toClusterID)

        # Select storage pool
        targetStorage = self.cosmic.getStoragePoolWithMostFreeSpace(self.toClusterID)
        targetStorageID = targetStorage.id
        targetStoragePoolData = self.cosmic.getStoragePoolData(targetStorageID)[0]
        storagepooltags = targetStoragePoolData.tags
        storagepoolname = targetStoragePoolData.name

        # Get hosts that belong to toCluster
        toClusterHostsData = self.cosmic.getHostsFromCluster(self.toClusterID)
        if self.DEBUG == 1:
            print "Note: You selected a storage pool with tags '" + str(storagepooltags) + "'"

        # SSH to random host on tocluster -> create migration folder
        if self.cosmic.kvm.prepare_kvm(self.kvm_host, targetStoragePoolData.id) is False:
            sys.exit(1)
        if self.cosmic.kvm.put_scripts(self.kvm_host) is False:
            sys.exit(1)

    def vmware_virt_v2v(self):
        self.cosmic.kvm.vmware_virt_v2v(self.kvm_host, self.esxiHost, self.vmxPath)

    def gather_disk_info(self):
        # Gather disk info from kvm host
        # disks = self.cosmic.kvm.get_disk_sizes(self.kvm_host).splitlines()

        disks = """10737418240 boris-test-01-sda
1073741824 boris-test-01-sdb
1073741824 boris-test-01-sdc"""

        for disk in disks.splitlines():
            self.disk_sizes[disk.split(' ')[1]] = {
                'size': int(disk.split(' ')[0]) / 1024 / 1024 / 1024  # Byte to GByte
            }

        self.disk_name = self.disk_sizes.keys()[0].split('-sd')[0]

    def deploy_vm(self):

        # Create virtualmachine
        self.cosmic.deployVirtualMachine({
            'name': self.instancename,
            'displayname': self.instancename,
            'startvm': 'false',
            'templateid': self.newBaseTemplate,
            'serviceofferingid': self.serviceOffering,
            'zoneid': self.zone,
            'account': self.account,
            'domainid': self.domain,
            'iptonetworklist': self.networkIp,
            'rootdisksize': self.disk_sizes[self.disk_name + '-sda']['size'],
            'hypervisor': 'KVM'
        })

    def add_data_disks(self):
        for disk in self.disk_sizes.keys():
            if '-sda' not in disk:
                pass
                self.cosmic.createVolume({
                    'name': self.instancename,
                    'zoneid': self.zone,
                    'account': self.account,
                    'domainid': self.domain,
                    'size': self.disk_sizes[disk]['size'],

                })


# TODO Add data disks
# TODO Start virtual machine
# TODO Stop virtual machine
# TODO Get disks locations from database
# TODO Move disks on kvm host to correct location
# TODO Start vm
# TODO Check if vm already exists before starting!
# TODO add --exec and --debug features


# Parse arguments
if __name__ == "__main__":
    app = migrateVirtualMachineFromVMwareToKVM()
    app.migrate()
