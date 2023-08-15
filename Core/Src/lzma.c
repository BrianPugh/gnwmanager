#include "lzma.h"
#include "LzmaDec.h"
#include "assert.h"


static void *SzAlloc(ISzAllocPtr p, size_t size) {
    void* res = p->Mem;
    return res;
}

static void SzFree(ISzAllocPtr p, void *address) {
}

const uint8_t lzma_prop_data[5] = {0x5d, 0x00, 0x40, 0x00, 0x00};

void lzma_init_allocs(ISzAlloc *allocs, uint8_t *heap){
    allocs->Alloc = SzAlloc;
    allocs->Free = SzFree;
    allocs->Mem = heap;
}

size_t lzma_inflate(uint8_t *dst, size_t dst_size, const uint8_t *src, size_t src_size){
    unsigned char lzma_heap[LZMA_BUF_SIZE];
    ISzAlloc allocs;
    lzma_init_allocs(&allocs, lzma_heap);

    ELzmaStatus status;
    SRes res;

    dst_size++;  // I think there's an off-by-one error in LzmaDecode
    res = LzmaDecode(dst, &dst_size, src, &src_size, lzma_prop_data, 5, LZMA_FINISH_ANY, &status, &allocs);

    if (res != SZ_OK){
        return 0;
    }
    if(res != LZMA_STATUS_FINISHED_WITH_MARK){
        return 0;
    }

    return dst_size;
}
