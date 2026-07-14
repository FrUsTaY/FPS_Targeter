"""
Подмена названия GPU для поиска бенчмарков.
P106-100 -> NVIDIA GeForce GTX 1060 6GB
"""


def get_search_gpu_name(real_gpu_name: str) -> str:
    if not real_gpu_name:
        return "NVIDIA GTX 1060 6GB"  # fallback
    if "p106-100" in real_gpu_name.lower():
        return "NVIDIA GeForce GTX 1060 6GB"
    return real_gpu_name
