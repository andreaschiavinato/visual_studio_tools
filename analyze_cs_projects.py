#
# This script scan a folder containing C# projects and generate a report
# of the references, NuGet packages and Net framework versions used
#

import sys
import os
import functools
import xml.etree.ElementTree as ElementTree
from yattag import Doc
import tempfile
import webbrowser
from nuget import *


class ProjectInfo:
    def __init__(self, file, target_framework_version, references, ng_packages):
        self.Name = self.__get_project_name(file)
        self.File = file
        self.TargetFrameworkVersion = target_framework_version
        self.References = references
        self.ng_packages = ng_packages

    def __repr__(self):
        return self.Name

    @staticmethod
    def __get_project_name(file):
        return os.path.splitext(os.path.basename(file))[0]


class Reference:
    def __init__(self, nuget_service_index, reference_name, nuget_packages):
        self.FullName = reference_name
        tokens = reference_name.split(",")
        self.Name = tokens[0]
        if len(tokens) > 1:
            self.Version = tokens[1].split("=")[1]
        else:
            self.Version = ""
        if nuget_packages is None:
            self.IsNuGetPackage = False
            self.LatestVersion = None
        else:
            self.IsNuGetPackage = any([p for p in nuget_packages if p.Id == self.Name])
            if self.IsNuGetPackage:
                metadata = NugetPackageMetadata(nuget_service_index, self.Name)
                self.LatestVersion = ", ".join(metadata.get_latest_version()) if self.IsNuGetPackage else None
            else:
                self.LatestVersion = None

    def __repr__(self):
        return self.Name


class NuGetPackage:
    def __init__(self, id, version, target_framework):
        self.Id = id
        self.Version = version
        self.TargetFramework = target_framework

    def __repr__(self):
        return self.Id


class ReferencesMatrix:
    def __init__(self, projects_info):
        self.uses = {}
        self.projects_info = projects_info
        nr_projects = len(projects_info)
        for project_id, project_info in enumerate(projects_info):
            if project_info.References is not None:
                for reference in project_info.References:
                    if reference not in self.uses:
                        self.uses[reference] = [False] * nr_projects
                    self.uses[reference][project_id] = True


class HtmlFormatter:
    def __init__(self, projects_info, reference_matrix):
        self.projects_info = projects_info
        self.reference_matrix = reference_matrix

    def get_output(self):
        doc, tag, text, line = Doc().ttl()
        doc.asis('<!DOCTYPE html>')
        with tag('html'):
            with tag('head'):
                with tag('style'):
                    text("table, th, td {border: 1px solid black; border-collapse: collapse; }")
            with tag('body'):
                with tag('div'):
                    doc.line('h1', '.NET Framework versions')
                    doc.asis(self.get_framework_table())
                with tag('div'):
                    doc.line('h1', 'References')
                    doc.asis(self.get_references_table())
        return doc.getvalue()

    def get_framework_table(self):
        doc, tag, text, line = Doc().ttl()
        with tag('table'):
            with tag('tr'):
                line('th', 'Project')
                line('th', 'TargetFrameworkVersion')
            for project in self.projects_info:
                with tag('tr'):
                    line('td', project.Name)
                    line('td', project.TargetFrameworkVersion if project.TargetFrameworkVersion is not None else "")
        return doc.getvalue()

    def get_references_table(self):
        doc, tag, text, line = Doc().ttl()
        with tag('table'):
            with tag('tr'):
                line('th', 'Reference')
                line('th', 'Version')
                line('th', 'IsNuGetPackage')
                line('th', 'LatestVersion')
                for project in self.projects_info:
                    line('th', project.Name)

            references = [ref for ref in self.reference_matrix.uses.keys()]
            for reference in sorted(references, key=lambda ref: ref.Name):
                with tag('tr'):
                    line('td', reference.Name)
                    line('td', reference.Version)
                    line('td', "Y" if reference.IsNuGetPackage else "N")
                    line('td', reference.LatestVersion if reference.LatestVersion is not None else "")
                    for projectid in range(len(self.projects_info)):
                        line('td', "*" if self.reference_matrix.uses[reference][projectid] else "")
        return doc.getvalue()


class ProjectsAnalyzer:
    def __init__(self, folder):
        files = self.__get_files_in_folder(folder, ".csproj")
        self.folder = folder
        self.all_references = {}
        self.nuget_service_index = NugetServiceIndex()
        print("Analyzing project files")
        self.projects_info = [self.__read_project_info(f) for f in files]
        self.reference_matrix = ReferencesMatrix(self.projects_info)
        print("Done")

    def generate_and_show_report(self):
        formatter = HtmlFormatter(self.projects_info, self.reference_matrix)
        filename = self.save_tmp_html(formatter.get_output())
        self.open_html(filename)

    def save_tmp_html(self, html):
        with tempfile.NamedTemporaryFile(mode='wt', delete=False, suffix=".html") as f:
            f.write(html)
            return f.name

    def open_html(self, filename):
        webbrowser.open('file://' + filename)

    def __read_project_info(self, file):
        ng_packages = self.__read_project_nuget_packages(file)

        tree = ElementTree.parse(file)
        root = tree.getroot()
        ns = "{http://schemas.microsoft.com/developer/msbuild/2003}"
        try:
            version = root.findall(f"{ns}PropertyGroup/{ns}TargetFrameworkVersion")[0].text
        except:
            version = None

        try:
            references_names = [reference.get("Include") for reference in root.findall(f"{ns}ItemGroup/{ns}Reference")]
            references = []
            for ref_name in references_names:
                if ref_name not in self.all_references:
                    self.all_references[ref_name] = Reference(self.nuget_service_index, ref_name, ng_packages)
                references.append(self.all_references[ref_name])
        except:
            references = []

        file_relative = file[len(self.folder):]
        return ProjectInfo(file_relative, version, references, ng_packages)

    def __read_project_nuget_packages(self, project_file):
        ng_file = os.path.dirname(project_file) + r"\packages.config"
        if os.path.isfile(ng_file):
            tree = ElementTree.parse(ng_file)
            root = tree.getroot()
            return [NuGetPackage(package.get("id"), package.get("version"), package.get("targetFramework"))
                    for package
                    in root.findall("package")]
        else:
            return None

    def __get_files_in_folder(self, folder, extension):
        files = [map(functools.partial(os.path.join, dirpath), filenames) for (dirpath, dirnames, filenames) in
                 os.walk(folder)
                 if len(filenames) > 0]
        files_flat = [item for sublist in files for item in sublist]
        extension = extension.upper()
        return [filename for filename in files_flat if os.path.splitext(filename)[1].upper() == extension]


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Provide a folder name as first command line argument")
    else:
        ProjectsAnalyzer(sys.argv[1]).generate_and_show_report()
