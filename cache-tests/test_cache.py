
from util.util_stage1 import *


# must be called before importing the other zmirror modules, so they will use the stub
insert_zpool_status_stub()

# only now must we import all the other zmirror modules, so that they will use the stub
from zmirror.daemon import handle
import zmirror.commands
from zmirror.dataclasses import *
import zmirror.config
from zmirror.zmirror import scrub
import zmirror.entities as entities
import zmirror.commands as commands


from util.util_stage2 import *

import pytest



zfs_blockdev_id = "ZFSBackingDeviceCache|zpool-a|partition-a"
partition_id = "Partition|partition-a"
dm_id= "DM_Crypt|dm-alpha"
disk_id = "Disk|0123456789abcdef"
zpool_id = "ZPool|zpool-a"
virtual_disk_id = "VirtualDisk|0123456789abcdef"
zfs_volume_id = "ZFSVolume|zpool-a|path/zfs-volume"
logical_volume_id = "LVMLogicalVolume|vg-alpha|lv-1"





@pytest.fixture(scope="class", autouse=True)
def setup_before_all_methods():
  # Code to execute once before all test methods in each class
  insert_zpool_status_stub()
  prepare_config_and_cache()



# this group of tests all require the daemon running, hence they are grouped
class Test_Group1_TestMethods():


  # event_queue = None

        


  def setup_method(self, method):
    # core.config_file_path = os.pardir(__file__) + "/config.yml"
    # load_config()
    # core.cache_file_path = "./run/test/state/cache.yml"
    # self.daemon_thread = threading.Thread(target=run_command, args=(["--state-dir", "./run/state", "--config-file", f"{get_current_module_directory()}/config.yml"], ))
    # self.daemon_thread.start()
    # if self.event_queue == None:
      # self.event_queue = queue.Queue()
    pass

  
  def teardown_method(self, method):
  
    # terminate_thread(self.daemon_thread)
    # silent_remove(core.cache_file_path)
    # pass
    commands.commands = []



  # # tatsächliches gerät wird angeschlossen

  # disk taucht auf (udev: add)
  def test_disk_add(self):

    assert disk_id not in config.cache_dict

    trigger_event()

    dev: Disk = config.cache_dict[disk_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.ONLINE)

    # assert("zpool offline xyz" in zmirror_commands.commands)


  # partition taucht auf (udev: add)
  def test_partition_add(self):
    
    assert partition_id not in config.cache_dict

    trigger_event()

    dev: Partition = config.cache_dict[partition_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.ONLINE)


  def test_zpool_online(self):
    assert zpool_id not in config.cache_dict
    trigger_event()
    assert zpool_id in config.cache_dict
    dev: ZPool = config.cache_dict[zpool_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.ONLINE)

  def test_zpool_offline(self):
    trigger_event()
    assert zpool_id in config.cache_dict
    dev: ZPool = config.cache_dict[zpool_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.DISCONNECTED)
  



  # # zmirror command: zpool online vdev
  # vdev wird im zpool aktiviert (vdev_online)
  def test_zdev_online(self):
    # it is already in the cache_dict because when we imported the pool
    # it came in through zpool status
    assert zfs_blockdev_id in config.cache_dict
    dev: ZFSBackingDeviceCache = config.cache_dict[zfs_blockdev_id]
    assert dev.state.what == EntityState.DISCONNECTED

    trigger_event()

    assert zfs_blockdev_id in config.cache_dict


    dev2: ZFSBackingDeviceCache = config.cache_dict[zfs_blockdev_id]

    assert dev is dev2
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.ONLINE)

    # now we change the status stub
    insert_zpool_status_stub("res/zpool-status-after-online.txt") 


  # vdev beginnt zu resilvern (resilver_start)
  def test_resilver_start(self):
    trigger_event()
    dev: ZFSBackingDeviceCache = config.cache_dict[zfs_blockdev_id]
    
    assert(dev is not None)
    assert(dev.operation.what== ZFSOperationState.RESILVERING)

  # vdev resilver ist abgeschlossen (resilver_finish)
  def test_resilver_finish(self):
    trigger_event()
    dev: ZFSBackingDeviceCache = config.cache_dict[zfs_blockdev_id]
    
    assert(dev is not None)
    assert(dev.operation.what == ZFSOperationState.NONE)

  # # zmirror started scrub
  # pool scrub startet (scrub_start)
  def test_scrub_start(self):
    trigger_event()
    dev: ZFSBackingDeviceCache = config.cache_dict[zfs_blockdev_id]
    
    assert(dev is not None)
    assert(dev.operation.what == ZFSOperationState.SCRUBBING)

  # pool scrub ist abgeschlossen (scrub_finish)
  def test_scrub_finish(self):
    trigger_event()
    dev: ZFSBackingDeviceCache = config.cache_dict[zfs_blockdev_id]
    
    assert(dev is not None)
    assert(dev.operation.what == ZFSOperationState.NONE)

  # # tatsächliches gerät wird abgetrennt
  # partition verschwindet (udev: remove)
  def test_partition_remove(self):
    trigger_event()

    dev: Partition = config.cache_dict[partition_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.DISCONNECTED)
    assert(dev.last_online is not None)
    assert(dev.last_online < datetime.now())

  # disk verschwindet (udev: remove)
  def test_disk_remove(self):
    trigger_event()

    dev: Disk = config.cache_dict[disk_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.DISCONNECTED)
    assert(dev.last_online != None)
    assert(dev.last_online < datetime.now())

  # # zmirror command: zpool offline vdev
  # vdev wird faulted (falls der zmirror command nich schneller ist)
  # vdev wird disconnected (falls der zmirror command nich schneller ist... außerdem kann es sein, dass alex sich irrt und disconnected gibt es nicht im zfs speak) 
  # vdev wird offline (weil zmirror den command geschickt hat)


  def test_zdev_disconnected(self):
    assert zfs_blockdev_id in config.cache_dict
    
    trigger_event()

    dev: ZFSBackingDevice = config.cache_dict[zfs_blockdev_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.DISCONNECTED)
    assert(dev.last_online != None)
    assert(dev.last_online < datetime.now())

  # # virtual disk taucht auf (udev: add)
  # def test_virtual_disk_add(self):
    
  #   config.cache_dict = dict()
  #   assert virtual_disk_id not in config.cache_dict

  #   trigger_event()

  #   assert virtual_disk_id in config.cache_dict
    
  #   dev: VirtualDisk = config.cache_dict[virtual_disk_id]
    
    
  #   assert(dev is not None)
  #   assert(dev.state.what == EntityState.ONLINE)

  # # virtual disk verschwindet (udev: remove)
  # def test_virtual_disk_remove(self):
    
  #   assert virtual_disk_id in config.cache_dict

  #   trigger_event()

  #   dev: VirtualDisk = config.cache_dict[virtual_disk_id]
    
  #   assert(dev is not None)
  #   assert(dev.state.what == EntityState.DISCONNECTED)
  #   assert(dev.last_online != None)
  #   assert(dev.last_online < datetime.now())

  # # logical volume taucht auf (udev: add)
  # def test_logical_volume_add(self):
    
  #   config.cache_dict = dict()
  #   assert logical_volume_id not in config.cache_dict

  #   trigger_event()
    
  #   assert logical_volume_id in config.cache_dict

  #   dev: LVMLogicalVolume = config.cache_dict[logical_volume_id]
    
    
  #   assert(dev is not None)
  #   assert(dev.state.what == EntityState.ONLINE)

  # # logical volume verschwindet (udev: remove)
  # def test_logical_volume_remove(self):
    
  #   assert logical_volume_id in config.cache_dict

  #   trigger_event()

  #   dev: LVMLogicalVolume = config.cache_dict[logical_volume_id]
    
  #   assert(dev is not None)
  #   assert(dev.state.what == EntityState.DISCONNECTED)
  #   assert(dev.last_online != None)
  #   assert(dev.last_online < datetime.now())


  # zfs_volume taucht auf (udev: add)
  def test_zfs_volume_add(self):
    
    config.cache_dict = dict()
    assert zfs_volume_id not in config.cache_dict

    trigger_event()

    assert zfs_volume_id in config.cache_dict
    
    dev: ZFSVolume = config.cache_dict[zfs_volume_id]
    
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.ONLINE)

  # zfs_volume verschwindet (udev: remove)
  def test_zfs_volume_remove(self):
    
    assert zfs_volume_id in config.cache_dict

    trigger_event()

    dev: ZFSVolume = config.cache_dict[zfs_volume_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.DISCONNECTED)
    assert(dev.last_online is not None)
    assert(dev.last_online < datetime.now())
    
    # process.kill()

if __name__ == '__main__':
    if False:
        test_methods = Test_Group1_TestMethods()
        test_methods.test_some_test1()
    else:
        pytest.main()