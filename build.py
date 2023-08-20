import subprocess


def main():
    subprocess.check_output(["make", "-j4"])


if __name__ == "__main__":
    main()
