import argparse
import os
import sys

# Represents a .cpp or .h file.
class CodeFile:
    def __init__(self, root, path, filename):
        """
        root: the root path to the source code
        path: the path after root before filename
        """
        self.root = root
        self.path = path
        self.filename = filename
        self.basename = filename.split('.')[0]
        self.hasFoundAllDependentFiles = False
        self.dependentFiles = set()

    def findDependentFiles(self, codeFilesByFilename):
        if self.hasFoundAllDependentFiles:
            return self.dependentFiles

        # First find the included files.
        includedFiles = []
        openedFile = open(self.root + self.path + self.filename)
        for line in openedFile:
            pathAndFilename = ""
            if line.startswith('#include'):
                if line[8:].find("\"") >= 0:
                    pathAndFilename = line[8:].strip().split("\"")[1]
                    includedFiles.append(codeFilesByFilename[pathAndFilename])

        # Then let the included files find their dependent files.
        self.dependentFiles.clear()
        for file in includedFiles:
            self.dependentFiles.add(file)
            self.dependentFiles.update(file.findDependentFiles(codeFilesByFilename))
        self.hasFoundAllDependentFiles = True
        return self.dependentFiles

    def getSortingKey(self):
        return self.path + self.filename

class Package:
    def __init__(self, root, path):
        self.root = root
        self.path = path
        self.cppFiles = []
        self.pathToRoot = './'
        for i in range(self.path.count('/')):
            self.pathToRoot += '../'
        self.content = ''   # Content of Makefile

    def addCppFile(self, codeFile):
        """
        Assume codeFile.filename.endswith('.cpp') is true.
        """
        self.cppFiles.append(codeFile)

    def generateMakefile(self):
        self.cppFiles.sort(key=lambda codeFile: codeFile.getSortingKey())

        self.content = ''
        self.printVariables()
        self.printTargetAll()
        self.printTargetExecutable()
        self.printTargetObjectFiles()
        self.printTargetClean()

        pathAndFilename = self.root + self.path + 'Makefile'
        file = open(pathAndFilename, 'w')
        file.write(self.content)
        file.close()

    # The following methods are called in generateMakefile().

    def printVariables(self):
        """
        Create variables of the compiler, include path and headers.
        Assume all CodeFiles have found their dependent files.
        """
        self.content += 'INC = -I ' + self.pathToRoot + '\n'

        # Headers
        for codeFile in self.cppFiles:
            variableName = 'HEADERS_' + codeFile.basename.upper()
            self.content += variableName + ' = '
            for dependentFile in sorted(codeFile.dependentFiles, key=lambda codeFile: codeFile.getSortingKey()):
                self.content += '\\\n\t' + self.pathToRoot + dependentFile.path + dependentFile.filename
            self.content += '\n\n'

    def printTargetAll(self):
        """
        Make all cpp files to object files.
        """
        self.content += 'all:\n'
        for codeFile in self.cppFiles:
            self.content += '\tmake ' + codeFile.basename + '.o\n'

    def printTargetExecutable(self):
        """
        Can be overridden.
        """
        pass

    def printTargetObjectFiles(self):
        for codeFile in self.cppFiles:
            basename = codeFile.basename
            self.content += basename + '.o: ' + basename + '.cpp '
            self.content += '$(HEADERS_' + basename.upper() + ')\n'
            self.content += '\t$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c ' + basename + '.cpp $(INC)\n'

    def printTargetClean(self):
        self.content += 'clean: \n\trm *.o\n'

class RootPackage(Package):
    def __init__(self, root, path, executableName, libs=[]):
        """
        allPackages: all packages in the project, including the root package
        libs: the names of libraries which is the string after '-l' in
            compiler commands.
        """
        super().__init__(root, path)
        self.allPackages = 0
        self.executableName = executableName
        self.libs = libs

    def setAllPackages(self, allPackages):
        self.allPackages = sorted(allPackages, key=lambda package: package.path)

    def printVariables(self):
        self.content += 'CXXFLAGS = -std=c++11\n'
        super().printVariables()

        # Object files
        self.content += 'OBJECTS = '
        for package in self.allPackages:
            self.content += '\\\n\t./' + package.path + '*.o'
        self.content += '\n\n'

        # Libraries
        self.content += 'LDLIBS ='
        for lib in self.libs:
            self.content += ' -l' + lib
        self.content += '\n\n'

    def printTargetAll(self):
        self.content += 'all:\n'
        for package in self.allPackages:
            if package == self:
                continue
            self.content += '\tcd ' + package.path + '; make all\n'
        for codeFile in self.cppFiles:
            self.content += '\tmake ' + codeFile.basename + '.o\n'
        self.content += '\tmake ' + self.executableName + '\n'

    def printTargetExecutable(self):
        self.content += self.executableName + ': $(OBJECTS)\n'
        self.content += '\t$(CXX) $(LDFLAGS) $(OBJECTS) $(LDLIBS) -o ' + self.executableName + '\n'

    def printTargetClean(self):
        self.content += 'clean:\n'
        for package in self.allPackages:
            if package == self:
                continue
            self.content += '\tcd ' + package.path + '; make clean\n'
        self.content += '\trm *.o ' + self.executableName + '\n'

def parseArguments(argv=0):
    parser = argparse.ArgumentParser()
    parser.add_argument('root',
        help='the path to the directory of main.cpp. \
        It starts with \'./\' and ends with \'/\'.')
    parser.add_argument('output',
        help='the name of the compiled executable')
    parser.add_argument('-l', '-libs',
        help='the libraries to be linked. \
        For example, if the compiler command is \n \
        \'g++ a.o -lb -lc\' \
        then the value of the argument here should be \'b,c\'.')
    if argv == 0:
        return parser.parse_args()
    else:
        return parser.parse_args(argv)

def main(argv):
    # Get arguments
    args = parseArguments()
    root = args.root
    executableName = args.output
    libs = [lib for lib in args.l.split(',')]

    # To store all Packages and CodeFiles.
    packages = []
    rootPackage = 0
    codeFiles = []
    codeFilesByFilename = dict()

    prevPath = 0
    package = 0
    for pathWithRoot, dirnames, filenames in os.walk(root):
        for filename in filenames:
            path = pathWithRoot[len(root):]
            isNotInRootPackage = False
            if len(path) > 0:   # Not the root path
                path += '/'
                isNotInRootPackage = True
            # Create a new Package
            if path != prevPath:
                if isNotInRootPackage:
                    package = Package(root, path)
                else:
                    package = RootPackage(root, path, executableName, libs=libs)
                    rootPackage = package
                packages.append(package)
                prevPath = path
            # Store the CodeFile
            if filename.endswith('.h') or filename.endswith('.cpp'):
                codeFile = CodeFile(root, path, filename)
                codeFiles.append(codeFile)
                codeFilesByFilename[path + filename] = codeFile
                if filename.endswith('.cpp'):
                    package.addCppFile(codeFile)

    rootPackage.setAllPackages(packages)

    # Find dependent files of the CodeFiles.
    for file in codeFiles:
        dependentFiles = file.findDependentFiles(codeFilesByFilename)

    # Generate makefiles.
    for package in packages:
        package.generateMakefile()

if __name__ == '__main__':
    main(sys.argv)