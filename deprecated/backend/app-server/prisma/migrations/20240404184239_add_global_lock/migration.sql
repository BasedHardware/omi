-- CreateTable
CREATE TABLE "GlobalLock" (
    "id" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "GlobalLock_pkey" PRIMARY KEY ("id")
);
