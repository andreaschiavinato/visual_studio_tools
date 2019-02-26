import requests


class NugetServiceIndex:
    def __init__(self):
        # see https://docs.microsoft.com/en-us/nuget/api/service-index
        self.api_index = requests.get(r"https://api.nuget.org/v3/index.json").json()

    def get_service_id(self, service_name):
        service = next(iter([x for x in self.api_index['resources'] if x['@type'] == service_name]))
        return service['@id']


class NugetPackageMetadata:
    def __init__(self, service_index, package_id):
        print(f"Getting info for NuGet package {package_id}")
        uri = service_index.get_service_id('RegistrationsBaseUrl')
        self.registration_info = requests.get(f"{uri}{package_id.lower()}/index.json").json()

    def get_latest_version(self):
        return [x['upper'] for x in self.registration_info['items']]
