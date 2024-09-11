import io
import tarfile


def build_extended_image(
    log, docker_client, base_image, run_commands, new_image_name
) -> str:
    """
    Build a new Docker image based on the base_image and extended with run_commands.

    :param docker_client: Docker client instance
    :param base_image: The base image to extend
    :param run_commands: List of commands to run in the new image
    :param new_image_tag: Tag for the new image
    :return: ID of the new image
    """

    # Write run_commands to a local temp file
    run_commands_str = "\n".join(run_commands)

    log("build-extended-image", f"Building extended image {new_image_name}...")
    log("build-extended-image", f"Commands: {run_commands_str}")

    container = docker_client.containers.create(
        base_image,
        command="tail -f /dev/null",
    )

    container.start()

    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        script_info = tarfile.TarInfo(name="run_commands.sh")
        script_info.size = len(run_commands_str)
        tar.addfile(script_info, io.BytesIO(run_commands_str.encode()))

    tar_stream.seek(0)

    container.put_archive("/tmp/", tar_stream.read())
    container.exec_run("tar -xf /tmp/run_commands.sh.tar -C /tmp")

    new_image = container.commit(repository=new_image_name)
    container.remove(force=True)

    log("build-extended-image", f"Built image {new_image.id}")

    return new_image.id
