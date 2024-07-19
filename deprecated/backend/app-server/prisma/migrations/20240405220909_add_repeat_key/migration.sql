-- CreateTable
CREATE TABLE "RepeatKey" (
    "key" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expiresAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "RepeatKey_pkey" PRIMARY KEY ("key")
);

-- AddForeignKey
ALTER TABLE "RepeatKey" ADD CONSTRAINT "RepeatKey_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
