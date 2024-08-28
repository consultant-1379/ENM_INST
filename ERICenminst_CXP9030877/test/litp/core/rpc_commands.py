class PuppetExecutionProcessor(object):
    def __init__(self, max_iterations=60, wait_interval=5):
        self.max_iterations = max_iterations
        self.wait_interval = wait_interval
        self.nodes = {}

    def trigger_and_wait(self, node_list):
        pass

    def wait(self, node_list, verify_disabled=True):
        pass


def run_rpc_command(nodes, agent, action,
                    action_kwargs=None, timeout=None, retries=0):
    return_data = {}
    for node in nodes:
        return_data[node] = {
            'errors': None,
            'data': {
                'retcode': 0,
                'out': '',
                'err': ''
            }
        }
    return return_data


class PuppetCatalogRunProcessor(object):
    def update_config_version(self):
        pass

    def trigger_and_wait(self, new_catalog_version, master_list):
        pass
