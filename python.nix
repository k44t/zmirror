{
  python3
}: 

(python3.withPackages (pythonPackages: with pythonPackages; [
  dateutil
  natsort
  datetime
  pyyaml
  jsonpickle
  dateparser
  systemd
  debugpy
]))

