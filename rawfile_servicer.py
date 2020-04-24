from pathlib import Path

from google.protobuf.wrappers_pb2 import BoolValue

from consts import DATA_DIR
from csi import csi_pb2, csi_pb2_grpc
from orchestrator.k8s import volume_to_node, run_on_node
from util import log_grpc_request, run
from remote import init_rawfile, scrub

NODE_NAME_TOPOLOGY_KEY = "hostname"


class RawFileIdentityServicer(csi_pb2_grpc.IdentityServicer):
    @log_grpc_request
    def GetPluginInfo(self, request, context):
        return csi_pb2.GetPluginInfoResponse(
            name="rawfile.hamravesh.com", vendor_version="0.0.1"
        )

    @log_grpc_request
    def GetPluginCapabilities(self, request, context):
        Cap = csi_pb2.PluginCapability
        return csi_pb2.GetPluginCapabilitiesResponse(
            capabilities=[
                Cap(service=Cap.Service(type=Cap.Service.CONTROLLER_SERVICE)),
                Cap(
                    service=Cap.Service(
                        type=Cap.Service.VOLUME_ACCESSIBILITY_CONSTRAINTS
                    )
                ),
            ]
        )

    @log_grpc_request
    def Probe(self, request, context):
        return csi_pb2.ProbeResponse(ready=BoolValue(value=True))


class RawFileNodeServicer(csi_pb2_grpc.NodeServicer):
    def __init__(self, node_name):
        self.node_name = node_name

    @log_grpc_request
    def NodeGetCapabilities(self, request, context):
        return csi_pb2.NodeGetCapabilitiesResponse(capabilities=[])

    @log_grpc_request
    def NodePublishVolume(self, request, context):
        mount_path = request.target_path
        img_dir = Path(f"{DATA_DIR}/{request.volume_id}")
        img_file = Path(f"{img_dir}/raw.img")

        run(f"mount {img_file} {mount_path}")
        return csi_pb2.NodePublishVolumeResponse()

    @log_grpc_request
    def NodeUnpublishVolume(self, request, context):
        mount_path = request.target_path
        run(f"umount {mount_path}")
        return csi_pb2.NodeUnpublishVolumeResponse()

    @log_grpc_request
    def NodeGetInfo(self, request, context):
        return csi_pb2.NodeGetInfoResponse(
            node_id=self.node_name,
            accessible_topology=csi_pb2.Topology(
                segments={NODE_NAME_TOPOLOGY_KEY: self.node_name}
            ),
        )


class RawFileControllerServicer(csi_pb2_grpc.ControllerServicer):
    @log_grpc_request
    def ControllerGetCapabilities(self, request, context):
        Cap = csi_pb2.ControllerServiceCapability
        return csi_pb2.ControllerGetCapabilitiesResponse(
            capabilities=[Cap(rpc=Cap.RPC(type=Cap.RPC.CREATE_DELETE_VOLUME))]
        )

    @log_grpc_request
    def CreateVolume(self, request, context):
        # TODO: volume_capabilities
        size = request.capacity_range.required_bytes
        node_name = request.accessibility_requirements.preferred[0].segments[
            NODE_NAME_TOPOLOGY_KEY
        ]

        run_on_node(
            init_rawfile.as_cmd(volume_id=request.name, size=size), node=node_name
        )

        return csi_pb2.CreateVolumeResponse(
            volume=csi_pb2.Volume(
                volume_id=request.name,
                capacity_bytes=size,
                accessible_topology=[
                    csi_pb2.Topology(segments={NODE_NAME_TOPOLOGY_KEY: node_name})
                ],
            )
        )

    @log_grpc_request
    def DeleteVolume(self, request, context):
        node_name = volume_to_node(request.volume_id)
        run_on_node(scrub.as_cmd(volume_id=request.volume_id), node=node_name)
        return csi_pb2.DeleteVolumeResponse()
